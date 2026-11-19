import base64
import binascii
import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Request,
    UploadFile,
    File,
    HTTPException,
)
from fastapi.security import APIKeyHeader
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ollama_client import ask_agent, process_email_order
from pdf_reader import extract_pdf_text

from test_pdf_bc_validation import (
    extract_order_json,
    normalize_order_numbers,
    extract_items_from_text,
    validate_order,
    validate_against_business_central,
    validate_inventory_availability,
    validate_customer_email,
)


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from the project's .env file.
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

FRONTEND_DIR = BASE_DIR / "frontend"

# Maximum decoded PDF size: 15 MB.
MAX_PDF_SIZE = 15 * 1024 * 1024

# Maximum Base64 length for a 15 MB PDF.
MAX_BASE64_LENGTH = 4 * ((MAX_PDF_SIZE + 2) // 3) + 100


app = FastAPI(
    title="AI Business Central Agent",
    description=(
        "AI-powered Business Central assistant with "
        "read-only purchase order validation."
    ),
    version="1.0.0",
)
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False
)
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }

    protected_paths = {
        "/chat",
        "/email-order",
        "/pdf-order",
        "/pdf-order-base64",
        "/create-approved-sales-order",
    }

    for path, methods in openapi_schema["paths"].items():
        if path in protected_paths:
            for method, details in methods.items():
                if method.lower() == "post":
                    details["security"] = [
                        {"APIKeyHeader": []}
                    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
# =========================================================
# API AUTHENTICATION
# =========================================================

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """
    Require X-API-Key for protected POST endpoints.

    Configure BC_AGENT_API_KEY in the .env file.
    """

    protected_paths = {
        "/chat",
        "/email-order",
        "/pdf-order",
        "/pdf-order-base64",
    }

    if (
        request.method == "POST"
        and request.url.path in protected_paths
    ):
        expected_key = os.getenv("BC_AGENT_API_KEY")
        supplied_key = request.headers.get(
            "X-API-Key", ""
        ).strip()

        if not expected_key:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "API authentication is not configured."
                    )
                },
            )

        if not secrets.compare_digest(
            supplied_key,
            expected_key.strip(),
        ):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid or missing API key."
                },
            )

    return await call_next(request)


# =========================================================
# REQUEST MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class EmailOrderRequest(BaseModel):
    email_text: str


class PdfBase64Request(BaseModel):
    filename: str
    file_content_base64: str


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def build_validation_section(
    errors: list[str],
    results: list[dict] | None = None,
    items_checked: int | None = None,
) -> dict:
    """Build a consistent validation-report section."""

    section = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }

    if results is not None:
        section["results"] = results

    if items_checked is not None:
        section["items_checked"] = items_checked

    return section


def skipped_validation_section(reason: str) -> dict:
    """Represent checks that were not executed."""

    return {
        "status": "SKIPPED",
        "items_checked": 0,
        "results": [],
        "errors": [],
        "reason": reason,
    }


def make_validation_report(
    filename: str,
    order: dict,
    customer: dict | None,
    customer_errors: list[str],
    document_errors: list[str],
    bc_results: list[dict],
    bc_errors: list[str],
    inventory_results: list[dict],
    inventory_errors: list[str],
    bc_checks_executed: bool,
    inventory_checks_executed: bool,
) -> dict:
    """Combine all validation outcomes into one JSON report."""

    all_errors = (
        customer_errors
        + document_errors
        + bc_errors
        + inventory_errors
    )

    overall_status = (
        "READY_FOR_REVIEW"
        if not all_errors
        else "MANUAL_REVIEW"
    )

    if document_errors:
        bc_section = skipped_validation_section(
            "Document validation failed; item checks were skipped."
        )

        inventory_section = skipped_validation_section(
            "Document validation failed; inventory checks were skipped."
        )

    else:
        if bc_checks_executed:
            bc_section = build_validation_section(
                bc_errors,
                bc_results,
                len(bc_results),
            )
        else:
            bc_section = skipped_validation_section(
                "Business Central item checks were not executed."
            )

        if inventory_checks_executed:
            inventory_section = build_validation_section(
                inventory_errors,
                inventory_results,
                len(inventory_results),
            )
        else:
            inventory_section = skipped_validation_section(
                "Inventory checks were not executed."
            )

    customer_section = build_validation_section(
        customer_errors
    )

    customer_section["customer_no"] = (
        customer.get("customer_no") if customer else None
    )

    customer_section["customer_name"] = (
        customer.get("name") if customer else None
    )

    return {
        "success": True,
        "filename": filename,

        "purchase_order": {
            "po_number": order.get("po_number"),
            "order_date": order.get("order_date"),
            "customer_email": order.get("customer_email"),
            "subtotal": order.get("subtotal"),
            "grand_total": order.get("grand_total"),
            "items": order.get("items", []),
        },

        "customer_validation": customer_section,

        "document_validation": {
            "status": (
                "PASS" if not document_errors else "FAIL"
            ),
            "items_extracted": len(order.get("items", [])),
            "errors": document_errors,
        },

        "business_central_item_validation": bc_section,

        "inventory_validation": inventory_section,

        "overall_status": overall_status,
        "total_validation_issues": len(all_errors),
        "validation_errors": all_errors,

        # This application currently performs validation only.
        "sales_order_created": False,
        "business_central_records_modified": False,
    }


# =========================================================
# PDF VALIDATION FUNCTION
# =========================================================

async def validate_pdf_bytes(
    filename: str,
    pdf_bytes: bytes,
) -> dict:
    """
    Run the existing read-only validation against PDF bytes.

    Both PDF endpoints use this shared function.
    """

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please provide a PDF file.",
        )

    if not pdf_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded PDF is empty.",
        )

    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="PDF exceeds the 15 MB size limit.",
        )

    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="The uploaded content is not a valid PDF.",
        )

    # 1. Extract PDF text.
    try:
        pdf_text = extract_pdf_text(pdf_bytes)

    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"PDF text extraction failed: {error}",
        ) from error

    if not pdf_text or not pdf_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "No readable text could be extracted from the PDF."
            ),
        )

    # 2. Extract order header using Ollama.
    try:
        order = extract_order_json(pdf_text)
        order = normalize_order_numbers(order)

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Purchase order header extraction failed: "
                f"{error}"
            ),
        ) from error

    # 3. Extract item rows using Python.
    try:
        items = extract_items_from_text(pdf_text)

    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "Purchase order item extraction failed: "
                f"{error}"
            ),
        ) from error

    order["items"] = items

    # 4. Validate document and arithmetic.
    document_errors = validate_order(order)

    if not items and not document_errors:
        document_errors.append(
            "No purchase order item rows were extracted."
        )

    # 5. Validate customer against Business Central.
    try:
        customer, customer_errors = validate_customer_email(
            order.get("customer_email")
        )

    except Exception as error:
        customer = None
        customer_errors = [
            f"Customer validation failed: {error}"
        ]

    # 6. Validate item master data in Business Central.
    bc_results = []
    bc_errors = []
    bc_checks_executed = False

    if not document_errors:
        bc_checks_executed = True

        try:
            bc_results, bc_errors = (
                validate_against_business_central(items)
            )

        except Exception as error:
            bc_errors.append(
                "Business Central item validation failed: "
                f"{error}"
            )

    # 7. Validate inventory availability.
    inventory_results = []
    inventory_errors = []
    inventory_checks_executed = False

    if not document_errors:
        inventory_checks_executed = True

        try:
            (
                inventory_results,
                inventory_errors,
            ) = validate_inventory_availability(items)

        except Exception as error:
            inventory_errors.append(
                f"Inventory validation failed: {error}"
            )

    # 8. Build the combined report.
    return make_validation_report(
        filename=filename,
        order=order,
        customer=customer,
        customer_errors=customer_errors,
        document_errors=document_errors,
        bc_results=bc_results,
        bc_errors=bc_errors,
        inventory_results=inventory_results,
        inventory_errors=inventory_errors,
        bc_checks_executed=bc_checks_executed,
        inventory_checks_executed=inventory_checks_executed,
    )


# =========================================================
# HOME PAGE
# =========================================================

@app.get("/")
def home():
    """Serve the frontend home page."""

    index_file = FRONTEND_DIR / "index.html"

    if not index_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Frontend index.html was not found.",
        )

    return FileResponse(str(index_file))


# =========================================================
# CHAT ENDPOINT
# =========================================================

@app.post("/chat")
def chat(request: ChatRequest):
    """Send a message to the existing AI agent."""

    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        response = ask_agent(
            request.message,
            request.session_id,
        )

        return {
            "success": True,
            "user_message": request.message,
            "session_id": request.session_id,
            "ai_response": response,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {error}",
        ) from error


# =========================================================
# EMAIL ORDER ENDPOINT
# =========================================================

@app.post("/email-order")
async def email_order(request: Request):
    """
    Receive an email from Power Automate.

    Supports JSON containing email_text, or raw UTF-8
    email text or HTML.
    """

    try:
        content_type = request.headers.get(
            "content-type",
            "",
        ).lower()

        raw_body = await request.body()

        if not raw_body:
            raise HTTPException(
                status_code=400,
                detail="Email body is empty.",
            )

        if "application/json" in content_type:
            try:
                data = json.loads(raw_body.decode("utf-8"))

            except (ValueError, UnicodeDecodeError) as error:
                raise HTTPException(
                    status_code=400,
                    detail="Request body contains invalid JSON.",
                ) from error

            if not isinstance(data, dict):
                raise HTTPException(
                    status_code=400,
                    detail="JSON body must be an object.",
                )

            email_text = data.get("email_text", "")

            if not isinstance(email_text, str):
                raise HTTPException(
                    status_code=400,
                    detail="email_text must be a string.",
                )

        else:
            email_text = raw_body.decode(
                "utf-8",
                errors="ignore",
            )

        if not email_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Email body is empty.",
            )

        return process_email_order(email_text)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Error processing email: {error}",
        ) from error


# =========================================================
# PDF PURCHASE ORDER VALIDATION ENDPOINT
# =========================================================

@app.post("/pdf-order")
async def process_pdf_order(
    file: UploadFile = File(...),
):
    """
    Receive a purchase order PDF as multipart form data.

    This endpoint is suitable for Swagger and clients that
    can construct multipart/form-data requests.
    """

    filename = file.filename or ""

    try:
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Please upload a PDF file.",
            )

        # Read at most one byte beyond the allowed limit.
        pdf_bytes = await file.read(MAX_PDF_SIZE + 1)

        return await validate_pdf_bytes(
            filename=filename,
            pdf_bytes=pdf_bytes,
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Could not process purchase order: {error}",
        ) from error

    finally:
        await file.close()


# =========================================================
# PDF BASE64 ENDPOINT FOR POWER AUTOMATE
# =========================================================

@app.post("/pdf-order-base64")
async def process_pdf_order_base64(
    request: PdfBase64Request,
):
    """
    Receive a Base64-encoded PDF in JSON from Power Automate.

    Expected JSON:
    {
        "filename": "Order_Letter.pdf",
        "file_content_base64": "<Base64 PDF content>"
    }

    This endpoint performs read-only validation only.
    """

    filename = request.filename.strip()
    encoded_content = request.file_content_base64.strip()

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please provide a PDF filename.",
        )

    if not encoded_content:
        raise HTTPException(
            status_code=400,
            detail="PDF content is empty.",
        )

    # Support an optional data URI prefix.
    if encoded_content.startswith("data:"):
        try:
            encoded_content = encoded_content.split(",", 1)[1]

        except IndexError as error:
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF data URI.",
            ) from error

    # Check encoded length before decoding to limit memory use.
    if len(encoded_content) > MAX_BASE64_LENGTH:
        raise HTTPException(
            status_code=413,
            detail="Encoded PDF exceeds the 15 MB size limit.",
        )

    try:
        pdf_bytes = base64.b64decode(
            encoded_content,
            validate=True,
        )

    except (ValueError, binascii.Error) as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid Base64 PDF content.",
        ) from error

    return await validate_pdf_bytes(
        filename=filename,
        pdf_bytes=pdf_bytes,
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health_check():
    """
    Confirm that the FastAPI service is running.

    This does not verify Ollama or Business Central connectivity.
    """

    return {
        "status": "running",
        "application": "AI Business Central Agent",
        "purchase_order_validation": "enabled",
        "sales_order_creation": False,
    }


# =========================================================
# STATIC FRONTEND
# =========================================================

if FRONTEND_DIR.is_dir():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="frontend",
    )
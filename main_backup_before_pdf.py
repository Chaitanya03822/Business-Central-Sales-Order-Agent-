from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ollama_client import (
    ask_agent,
    process_email_order
)

import os
import json


app = FastAPI(title="AI Business Central Agent")


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class EmailOrderRequest(BaseModel):
    email_text: str


FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "frontend"
)


@app.get("/")
def home():
    return FileResponse(
        os.path.join(FRONTEND_DIR, "index.html")
    )


@app.post("/chat")
def chat(request: ChatRequest):
    response = ask_agent(
        request.message,
        request.session_id
    )

    return {
        "user_message": request.message,
        "session_id": request.session_id,
        "ai_response": response
    }


@app.post("/email-order")
async def email_order(request: Request):
    """
    Receives an email from Power Automate.

    Power Automate/Outlook may send the email body as:
    1. JSON:
       {
           "email_text": "..."
       }

    or
    2. Raw HTML/text.

    This endpoint supports both formats.
    """

    try:
        content_type = request.headers.get(
            "content-type",
            ""
        ).lower()

        raw_body = await request.body()

        # ---------------------------------------------------------
        # Case 1: Power Automate sends JSON
        # ---------------------------------------------------------
        if "application/json" in content_type:

            try:
                data = json.loads(
                    raw_body.decode("utf-8")
                )

                email_text = data.get(
                    "email_text",
                    ""
                )

            except Exception:
                email_text = raw_body.decode(
                    "utf-8",
                    errors="ignore"
                )

        # ---------------------------------------------------------
        # Case 2: Power Automate sends raw HTML/text
        # ---------------------------------------------------------
        else:
            email_text = raw_body.decode(
                "utf-8",
                errors="ignore"
            )

        if not email_text.strip():
            return {
                "success": False,
                "message": "Email body is empty."
            }

        # ---------------------------------------------------------
        # Process the email order
        # ---------------------------------------------------------
        result = process_email_order(
            email_text
        )

        return result

    except Exception as e:

        return {
            "success": False,
            "message": "Error processing email order.",
            "error": str(e)
        }


app.mount(
    "/frontend",
    StaticFiles(directory=FRONTEND_DIR),
    name="frontend"
)
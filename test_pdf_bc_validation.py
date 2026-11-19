
import json
import re
from datetime import datetime

import requests

from matching_engine import compare_text, classify_match
from bc_client import (
    get_item_details,
    get_inventory,
    search_customers,
    get_all_customers,
)


# ==========================================================
# CONFIGURATION
# ==========================================================

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"


# ==========================================================
# STEP 1: NORMALIZE NUMERIC VALUES
# ==========================================================

def normalize_order_numbers(order: dict) -> dict:
    """Convert extracted monetary and quantity values to numbers."""

    if not isinstance(order, dict):
        raise ValueError("Order must be a dictionary.")

    for field in ("subtotal", "grand_total"):
        value = order.get(field)

        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()

            try:
                order[field] = float(cleaned)
            except ValueError:
                pass

    for item in order.get("items", []):
        if not isinstance(item, dict):
            continue

        for field in ("quantity", "unit_price", "line_total"):
            value = item.get(field)

            if isinstance(value, str):
                cleaned = value.replace("$", "").replace(",", "").strip()

                try:
                    number = float(cleaned)
                    item[field] = (
                        int(number) if number.is_integer() else number
                    )
                except ValueError:
                    pass

    return order


# ==========================================================
# STEP 2: EXTRACT ORDER HEADER USING OLLAMA
# ==========================================================

def extract_order_json(pdf_text: str) -> dict:
    """
    Extract purchase order header using Ollama,
    with regex fallbacks for important fields.
    """

    prompt = f"""
You are a purchase order extraction assistant.

Extract the purchase order header.

Return valid JSON only:

{{
    "customer_name": null,
    "customer_email": null,
    "po_number": null,
    "order_date": null,
    "currency": null,
    "subtotal": null,
    "grand_total": null
}}

Rules:
- Extract the actual customer/company name from BILL TO.
- Do not return section headings as customer names.
- Extract the customer email if present.
- Extract the currency code or symbol if present.
- Extract the order date exactly as printed.
- Extract subtotal and grand total as numeric values.
- Do not invent missing values.
- Do not use the supplier name as the customer name.
- Return null when information is not available.

DOCUMENT:
{pdf_text}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=180,
    )

    response.raise_for_status()

    content = response.json().get("response", "").strip()

    if not content:
        raise ValueError("Ollama returned an empty response.")

    try:
        order = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Ollama returned invalid JSON: {error}"
        ) from error

    if not isinstance(order, dict):
        raise ValueError("Ollama response must be a JSON object.")

    # ------------------------------------------------------
    # 1. CUSTOMER NAME VALIDATION
    # ------------------------------------------------------

    invalid_customer_names = {
        "BILL TO",
        "SHIP TO",
        "SOLD TO",
        "CUSTOMER",
        "SUPPLIER",
        "VENDOR",
        "CONTACT",
        "EMAIL",
    }

    customer_name = order.get("customer_name")

    if isinstance(customer_name, str):
        customer_name = customer_name.strip()

        if customer_name.upper() in invalid_customer_names:
            order["customer_name"] = None
        else:
            order["customer_name"] = customer_name

    # ------------------------------------------------------
    # 2. CUSTOMER EMAIL FALLBACK
    # ------------------------------------------------------

    if not order.get("customer_email"):
        email_matches = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            pdf_text,
        )

        if len(email_matches) == 1:
            order["customer_email"] = email_matches[0]

        elif len(email_matches) > 1:
            order["customer_email"] = None
            order["email_extraction_status"] = "MULTIPLE_EMAILS_FOUND"

    # ------------------------------------------------------
    # 3. CURRENCY FALLBACK
    # ------------------------------------------------------

    if not order.get("currency"):
        if "$" in pdf_text:
            order["currency"] = "USD"
        elif "€" in pdf_text:
            order["currency"] = "EUR"
        elif "£" in pdf_text:
            order["currency"] = "GBP"
        elif "₹" in pdf_text:
            order["currency"] = "INR"

    # ------------------------------------------------------
    # 4. ORDER DATE FALLBACK
    # ------------------------------------------------------

    if not order.get("order_date"):
        date_match = re.search(
            r"Order\s+Date\s*[\r\n]+(\d{2}[-/]\d{2}[-/]\d{4})",
            pdf_text,
            re.IGNORECASE,
        )

        if date_match:
            order["order_date"] = date_match.group(1)

    # ------------------------------------------------------
    # 5. SUBTOTAL FALLBACK
    # ------------------------------------------------------

    if order.get("subtotal") is None:
        subtotal_match = re.search(
            r"Subtotal\s*[\r\n]+\$?\s*([\d,]+(?:\.\d{2})?)",
            pdf_text,
            re.IGNORECASE,
        )

        if subtotal_match:
            order["subtotal"] = subtotal_match.group(1)

    # ------------------------------------------------------
    # 6. GRAND TOTAL FALLBACK
    # ------------------------------------------------------

    if order.get("grand_total") is None:
        total_match = re.search(
            r"Grand\s+Total\s*[\r\n]+\$?\s*([\d,]+(?:\.\d{2})?)",
            pdf_text,
            re.IGNORECASE,
        )

        if total_match:
            order["grand_total"] = total_match.group(1)

    # ------------------------------------------------------
    # 7. FINAL NUMERIC NORMALIZATION
    # ------------------------------------------------------

    return normalize_order_numbers(order)


# ==========================================================
# STEP 3: EXTRACT ITEM ROWS FROM PDF TEXT
# ==========================================================

def extract_items_from_text(pdf_text: str) -> list[dict]:
    """
    Extract item rows from the line-by-line PDF text.

    Expected sample layout:
    Item number
    Description
    Quantity
    Unit price
    Line total

    Different PDF layouts may require a different parser.
    """

    lines = [
        line.strip()
        for line in pdf_text.splitlines()
        if line.strip()
    ]

    items = []

    item_number_pattern = re.compile(r"^\d{4}-S$")
    quantity_pattern = re.compile(r"^\d+$")
    money_pattern = re.compile(r"^\$?\s*[\d,]+\.\d{2}$")

    i = 0

    while i < len(lines):

        if not item_number_pattern.fullmatch(lines[i]):
            i += 1
            continue

        if i + 4 >= len(lines):
            break

        item_number = lines[i]
        description = lines[i + 1]
        quantity_text = lines[i + 2]
        unit_price_text = lines[i + 3]
        line_total_text = lines[i + 4]

        if not quantity_pattern.fullmatch(quantity_text):
            i += 1
            continue

        if not money_pattern.fullmatch(unit_price_text):
            i += 1
            continue

        if not money_pattern.fullmatch(line_total_text):
            i += 1
            continue

        unit_price = float(
            unit_price_text.replace("$", "").replace(",", "").strip()
        )

        line_total = float(
            line_total_text.replace("$", "").replace(",", "").strip()
        )

        items.append({
            "item_number": item_number,
            "item_description": description,
            "quantity": int(quantity_text),
            "unit_price": unit_price,
            "line_total": line_total,
        })

        i += 5

    return items


# ==========================================================
# STEP 4: VALIDATE DOCUMENT DATA
# ==========================================================

def validate_order(order: dict) -> list[str]:
    """
    Validate document structure and arithmetic.

    Customer email is deliberately not mandatory here.
    Customer identity is checked separately.
    """

    errors = []

    if not isinstance(order, dict):
        return ["Order data must be a dictionary."]

    po_number = order.get("po_number")

    if not isinstance(po_number, str) or not po_number.strip():
        errors.append("Purchase order number is missing or invalid.")

    order_date = order.get("order_date")

    if not isinstance(order_date, str) or not order_date.strip():
        errors.append("Order date is missing.")

    else:
        valid_date = False

        for date_format in (
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
        ):
            try:
                datetime.strptime(order_date.strip(), date_format)
                valid_date = True
                break
            except ValueError:
                continue

        if not valid_date:
            errors.append(
                f"Order date '{order_date}' has an unsupported format."
            )

    items = order.get("items")

    if not isinstance(items, list) or not items:
        errors.append("No valid order items were extracted.")
        return errors

    seen_item_numbers = set()
    calculated_lines = []
    valid_line_count = 0

    for index, item in enumerate(items, start=1):

        if not isinstance(item, dict):
            errors.append(f"Item {index}: item data is invalid.")
            continue

        item_number = item.get("item_number")

        if not isinstance(item_number, str) or not item_number.strip():
            errors.append(f"Item {index}: item number is missing.")

        else:
            normalized_number = item_number.strip().casefold()

            if normalized_number in seen_item_numbers:
                errors.append(
                    f"{item_number}: duplicate item line detected."
                )
            else:
                seen_item_numbers.add(normalized_number)

        description = item.get("item_description")

        if not isinstance(description, str) or not description.strip():
            errors.append(
                f"Item {index}: item description is missing."
            )

        quantity = item.get("quantity")

        if (
            not isinstance(quantity, (int, float))
            or isinstance(quantity, bool)
            or quantity <= 0
        ):
            errors.append(
                f"Item {index} ({item_number}): "
                "quantity must be positive."
            )
            continue

        unit_price = item.get("unit_price")

        if (
            not isinstance(unit_price, (int, float))
            or isinstance(unit_price, bool)
            or unit_price < 0
        ):
            errors.append(
                f"Item {index} ({item_number}): "
                "unit price is invalid."
            )
            continue

        line_total = item.get("line_total")

        if (
            not isinstance(line_total, (int, float))
            or isinstance(line_total, bool)
            or line_total < 0
        ):
            errors.append(
                f"Item {index} ({item_number}): "
                "line total is invalid."
            )
            continue

        expected_total = round(quantity * unit_price, 2)
        actual_total = round(line_total, 2)

        if abs(actual_total - expected_total) > 0.01:
            errors.append(
                f"{item_number}: line total mismatch. "
                f"Expected {expected_total:.2f}, "
                f"received {actual_total:.2f}."
            )

        calculated_lines.append(actual_total)
        valid_line_count += 1

    subtotal = order.get("subtotal")

    if (
        not isinstance(subtotal, (int, float))
        or isinstance(subtotal, bool)
        or subtotal < 0
    ):
        errors.append("Subtotal is missing or invalid.")

    elif valid_line_count == len(items):

        calculated_subtotal = round(sum(calculated_lines), 2)

        if abs(round(subtotal, 2) - calculated_subtotal) > 0.01:
            errors.append(
                f"Subtotal mismatch. Calculated "
                f"{calculated_subtotal:.2f}, "
                f"received {subtotal:.2f}."
            )

    grand_total = order.get("grand_total")

    if (
        not isinstance(grand_total, (int, float))
        or isinstance(grand_total, bool)
        or grand_total < 0
    ):
        errors.append("Grand total is missing or invalid.")

    elif (
        isinstance(subtotal, (int, float))
        and not isinstance(subtotal, bool)
        and subtotal >= 0
        and abs(round(grand_total, 2) - round(subtotal, 2)) > 0.01
    ):
        errors.append(
            "Grand total differs from subtotal. "
            "Review tax, freight, discounts, and other charges."
        )

    return errors


# ==========================================================
# STEP 5: VALIDATE ITEMS AGAINST BUSINESS CENTRAL
# ==========================================================

def validate_against_business_central(
    items: list[dict],
) -> tuple[list[dict], list[str]]:

    results = []
    errors = []

    for item in items:

        item_number = item.get("item_number")

        if not item_number:
            errors.append("Item number is missing.")
            continue

        try:
            bc_item = get_item_details(item_number)

        except Exception as error:

            errors.append(
                f"{item_number}: Business Central lookup failed: {error}"
            )

            results.append({
                "item_number": item_number,
                "status": "LOOKUP_FAILED",
                "approved_for_validation": False,
            })

            continue

        if not isinstance(bc_item, dict) or bc_item.get("error"):

            errors.append(
                f"{item_number}: item not found or lookup failed."
            )

            results.append({
                "item_number": item_number,
                "status": "ITEM_NOT_FOUND",
                "approved_for_validation": False,
            })

            continue

        pdf_description = str(
            item.get("item_description") or ""
        ).strip()

        bc_description = str(
            bc_item.get("description") or ""
        ).strip()

        comparison = compare_text(
            pdf_description,
            bc_description,
        )

        score = comparison["score"]
        match_status = classify_match(score)

        description_matches = (
            match_status == "HIGH_CONFIDENCE"
        )

        # The standard item price is informational only.
        # It is NOT customer-specific sales price validation.
        standard_item_price = bc_item.get("unit_price")

        blocked = bc_item.get("blocked")
        is_unblocked = blocked is False

        result = {
            "item_number": item_number,
            "pdf_description": pdf_description,
            "bc_description": bc_description,
            "description_similarity": score,
            "description_match_status": match_status,
            "description_matches": description_matches,
            "pdf_unit_price": item.get("unit_price"),
            "bc_standard_unit_price": standard_item_price,
            "customer_specific_price_status": "NOT_CHECKED",
            "currency_validation_status": "NOT_CHECKED",
            "blocked": blocked,
            "is_unblocked": is_unblocked,
            "approved_for_validation": (
                description_matches and is_unblocked
            ),
        }

        results.append(result)

        if not description_matches:
            errors.append(
                f"{item_number}: description requires "
                f"review. Similarity={score}%."
            )

        if not is_unblocked:
            errors.append(
                f"{item_number}: item is blocked or blocked "
                "status could not be confirmed."
            )

    return results, errors


# ==========================================================
# STEP 6: VALIDATE INVENTORY AVAILABILITY
# ==========================================================

def validate_inventory_availability(
    items: list[dict],
) -> tuple[list[dict], list[str]]:

    results = []
    errors = []

    print("\n===== BUSINESS CENTRAL INVENTORY =====")

    for item in items:

        item_number = item.get("item_number")
        requested_qty = item.get("quantity")

        if not item_number:
            errors.append("Item number is missing.")
            continue

        if (
            not isinstance(requested_qty, (int, float))
            or isinstance(requested_qty, bool)
            or requested_qty <= 0
        ):
            errors.append(
                f"{item_number}: requested quantity is invalid."
            )
            continue

        try:
            inventory_data = get_inventory(item_number)

        except Exception as error:

            errors.append(
                f"{item_number}: inventory lookup failed: {error}"
            )

            results.append({
                "item_number": item_number,
                "status": "LOOKUP_FAILED",
            })

            continue

        if not isinstance(inventory_data, dict) or inventory_data.get("error"):

            errors.append(
                f"{item_number}: inventory could not be retrieved."
            )

            results.append({
                "item_number": item_number,
                "status": "LOOKUP_FAILED",
            })

            continue

        blocked = inventory_data.get("blocked")

        if blocked is not False:

            errors.append(
                f"{item_number}: item is blocked or blocked "
                "status is unknown."
            )

            results.append({
                "item_number": item_number,
                "status": "BLOCKED_OR_UNKNOWN",
            })

            continue

        raw_inventory = inventory_data.get("inventory")

        try:
            available_qty = float(raw_inventory)

        except (TypeError, ValueError):

            errors.append(
                f"{item_number}: inventory quantity is unavailable."
            )

            results.append({
                "item_number": item_number,
                "status": "INVENTORY_UNKNOWN",
            })

            continue

        if available_qty < requested_qty:

            status = "INSUFFICIENT_INVENTORY"

            errors.append(
                f"{item_number}: requested {requested_qty}, "
                f"available {available_qty}."
            )

        else:
            status = "PASS"

        result = {
            "item_number": item_number,
            "description": inventory_data.get("description"),
            "requested_qty": requested_qty,
            "available_inventory": available_qty,
            "status": status,
        }

        results.append(result)
        print(json.dumps(result, indent=2))

    return results, errors


# ==========================================================
# STEP 7: VALIDATE CUSTOMER AGAINST BUSINESS CENTRAL
# ==========================================================

def validate_customer_email(
    email: str,
    customer_name: str | None = None,
) -> tuple[dict | None, list[str]]:

    if not isinstance(email, str) or not email.strip():

        return None, [
            "Customer email is missing. Manual customer verification required."
        ]

    email = email.strip().casefold()

    try:
        customers = search_customers(email)

    except Exception as error:

        return None, [
            f"Business Central customer lookup failed: {error}"
        ]

    if not isinstance(customers, list):

        return None, [
            "Business Central returned an invalid customer response."
        ]

    exact_matches = [
        customer
        for customer in customers
        if isinstance(customer, dict)
        and isinstance(customer.get("email"), str)
        and customer["email"].strip().casefold() == email
    ]

    if len(exact_matches) == 0:

        # Search by name only to identify possible candidates.
        # Never automatically select a customer based on fuzzy name alone.

        if customer_name and customer_name.strip():

            try:
                all_customers = get_all_customers()

            except Exception as error:

                return None, [
                    f"Customer name lookup failed: {error}"
                ]

            ranked = []

            for candidate in all_customers:

                comparison = compare_text(
                    customer_name,
                    candidate.get("name"),
                )

                ranked.append((
                    comparison["score"],
                    candidate,
                ))

            ranked.sort(
                key=lambda row: row[0],
                reverse=True,
            )

            if ranked and ranked[0][0] >= 70:

                best_score, best_customer = ranked[0]

                return best_customer, [
                    "Possible customer name match found, "
                    "but email did not match. "
                    f"Similarity={best_score:.2f}%. "
                    "Manual verification required."
                ]

        return None, [
            f"No exact customer email match found for '{email}'."
        ]

    if len(exact_matches) > 1:

        return None, [
            "Multiple customers have the same email. "
            "Manual review required."
        ]

    customer = exact_matches[0]

    if not customer.get("customer_no"):

        return customer, [
            "Customer number is missing."
        ]

    if customer.get("blocked") is not False:

        return customer, [
            "Customer is blocked or blocked status "
            "could not be confirmed."
        ]

    if customer_name and customer.get("name"):

        comparison = compare_text(
            customer_name,
            customer.get("name"),
        )

        decision = classify_match(
            comparison["score"],
            auto_threshold=90.0,
            review_threshold=80.0,
        )

        customer["pdf_customer_name"] = customer_name
        customer["name_similarity_score"] = comparison["score"]
        customer["name_match_decision"] = decision

        if decision != "HIGH_CONFIDENCE":

            return customer, [
                "Customer email matched, but customer name "
                "requires manual review."
            ]

    return customer, []


# ==========================================================
# STEP 8: VALIDATE DOCUMENT CURRENCY
# ==========================================================

def validate_currency(
    pdf_currency: str | None,
    bc_currency: str | None = None,
) -> tuple[str, list[str]]:
    """
    Compare document currency with the customer's BC currency.

    This function requires the actual currency value from
    Business Central. It does not assume that blank currency
    means USD, INR, or any other currency.
    """

    if not pdf_currency:

        return "MANUAL_REVIEW", [
            "Document currency could not be identified."
        ]

    if bc_currency is None:

        return "NOT_CHECKED", [
            "Business Central customer currency was not supplied. "
            "Currency verification is pending."
        ]

    pdf_value = pdf_currency.strip().upper()
    bc_value = bc_currency.strip().upper()

    if pdf_value == bc_value:
        return "PASS", []

    return "FAIL", [
        f"Currency mismatch: PDF={pdf_value}, "
        f"Business Central={bc_value}."
    ]


# ==========================================================
# STEP 9: CUSTOMER-SPECIFIC PRICE VALIDATION STATUS
# ==========================================================

def customer_price_validation_status() -> dict:
    """
    Customer-specific sales price validation is intentionally
    not marked as passed until the correct BC sales-price source
    and API fields are confirmed.
    """

    return {
        "status": "NOT_IMPLEMENTED",
        "message": (
            "Customer-specific sales price has not been verified. "
            "Do not use the standard item price as a substitute."
        ),
    }

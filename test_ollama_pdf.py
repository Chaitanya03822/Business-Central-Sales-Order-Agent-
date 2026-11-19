
import json
import re
from pathlib import Path

import requests

from pdf_reader import extract_pdf_text


PDF_PATH = Path(r"C:\AI-BC-Agent\Order_Letter.pdf")
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"


# --------------------------------------------------
# STEP 1: EXTRACT ORDER HEADER DETAILS USING OLLAMA
# --------------------------------------------------

def extract_order_json(pdf_text: str) -> dict:
    prompt = f"""
You are a purchase order extraction assistant.

Extract the order header information from the document.
Return valid JSON only. Do not invent missing values.

Use this exact structure:
{{
  "customer_email": null,
  "po_number": null,
  "order_date": null,
  "subtotal": null,
  "grand_total": null
}}

Rules:
- Extract the purchase order number and date.
- Extract the contact email if present.
- Extract the subtotal and grand total if explicitly shown.
- Use JSON numbers for monetary amounts.
- Use null for missing information.
- Do not extract or create the items array.
- Do not guess missing values.

DOCUMENT TEXT:
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
        raise ValueError("Ollama output must be a JSON object.")

    return order


# --------------------------------------------------
# STEP 2: CONVERT NUMERIC STRINGS INTO NUMBERS
# --------------------------------------------------

def to_number(value):
    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()

        try:
            number = float(cleaned)

            if number.is_integer():
                return int(number)

            return number

        except ValueError:
            return value

    return value


def normalize_order_numbers(order: dict) -> dict:
    for field in ("subtotal", "grand_total"):
        order[field] = to_number(order.get(field))

    items = order.get("items", [])

    if not isinstance(items, list):
        raise ValueError("'items' must be a JSON list.")

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every item must be a JSON object.")

        for field in ("quantity", "unit_price", "line_total"):
            item[field] = to_number(item.get(field))

    return order


# --------------------------------------------------
# STEP 3: EXTRACT ITEM ROWS DIRECTLY FROM OCR TEXT
# --------------------------------------------------

def extract_items_from_text(pdf_text: str) -> list[dict]:
    """
    Extract item rows from the OCR text.

    Expected row format:
    Item No. | Description | Quantity | Unit Price | Total

    This parser is designed for the current test document layout.
    """

    pattern = re.compile(
        r"(?m)^\s*"
        r"(?P<item_number>\d{4}-S)\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<quantity>\d+)\s+"
        r"(?P<unit_price>\d[\d,]*\.\d{2})\s+"
        r"(?P<line_total>\d[\d,]*\.\d{2})"
        r"\s*$"
    )

    items = []

    for match in pattern.finditer(pdf_text):
        items.append({
            "item_number": match.group("item_number"),
            "item_description": match.group("description").strip(),
            "quantity": int(match.group("quantity")),
            "unit_price": float(
                match.group("unit_price").replace(",", "")
            ),
            "line_total": float(
                match.group("line_total").replace(",", "")
            ),
        })

    return items


# --------------------------------------------------
# STEP 4: VALIDATE ITEM ARITHMETIC AND SUBTOTAL
# --------------------------------------------------

def validate_order(order: dict) -> list[str]:
    errors = []
    items = order.get("items", [])

    if not items:
        errors.append("No order items were extracted.")
        return errors

    calculated_lines = []

    for index, item in enumerate(items, start=1):
        quantity = item.get("quantity")
        unit_price = item.get("unit_price")
        line_total = item.get("line_total")

        if (
            not isinstance(quantity, (int, float))
            or isinstance(quantity, bool)
            or quantity <= 0
        ):
            errors.append(f"Item {index}: invalid quantity.")
            continue

        if (
            not isinstance(unit_price, (int, float))
            or isinstance(unit_price, bool)
            or unit_price < 0
        ):
            errors.append(f"Item {index}: invalid unit price.")
            continue

        if (
            not isinstance(line_total, (int, float))
            or isinstance(line_total, bool)
            or line_total < 0
        ):
            errors.append(f"Item {index}: invalid line total.")
            continue

        expected_total = round(quantity * unit_price, 2)

        if abs(line_total - expected_total) > 0.01:
            errors.append(
                f"Item {index}: quantity x unit price does not "
                f"match line total. Expected {expected_total:.2f}, "
                f"received {line_total:.2f}."
            )

        calculated_lines.append(line_total)

    subtotal = order.get("subtotal")

    if (
        isinstance(subtotal, (int, float))
        and not isinstance(subtotal, bool)
        and len(calculated_lines) == len(items)
    ):
        calculated_subtotal = round(sum(calculated_lines), 2)

        if abs(subtotal - calculated_subtotal) > 0.01:
            errors.append(
                f"Subtotal mismatch. Expected "
                f"{calculated_subtotal:.2f}, received {subtotal:.2f}."
            )

    return errors


# --------------------------------------------------
# STEP 5: VALIDATE THE SAMPLE PURCHASE ORDER
# --------------------------------------------------

def validate_against_test_document(order: dict) -> list[str]:
    """
    This validation is specific to our sample Purchase Order.
    """

    errors = []
    items = order.get("items", [])

    expected_items = [
        {
            "item_number": "1896-S",
            "item_description": "ATHENS Desk",
            "quantity": 5,
            "unit_price": 506.60,
            "line_total": 2533.00,
        },
        {
            "item_number": "1920-S",
            "item_description": "PARIS Guest Chair, black",
            "quantity": 10,
            "unit_price": 192.80,
            "line_total": 1928.00,
        },
        {
            "item_number": "1900-S",
            "item_description": "Conference Package 1",
            "quantity": 2,
            "unit_price": 651.70,
            "line_total": 1303.40,
        },
    ]

    if len(items) != len(expected_items):
        errors.append(
            f"Expected {len(expected_items)} item rows, "
            f"but extracted {len(items)}."
        )

    for expected in expected_items:
        item_number = expected["item_number"]

        matches = [
            item for item in items
            if item.get("item_number") == item_number
        ]

        if len(matches) != 1:
            errors.append(
                f"Expected exactly one item with number "
                f"{item_number}; found {len(matches)}."
            )
            continue

        actual = matches[0]

        for field, expected_value in expected.items():
            actual_value = actual.get(field)

            if isinstance(expected_value, (int, float)):
                if (
                    not isinstance(actual_value, (int, float))
                    or isinstance(actual_value, bool)
                    or abs(actual_value - expected_value) > 0.01
                ):
                    errors.append(
                        f"{item_number}: {field} should be "
                        f"{expected_value}, received {actual_value}."
                    )

            elif actual_value != expected_value:
                errors.append(
                    f"{item_number}: {field} should be "
                    f"'{expected_value}', received '{actual_value}'."
                )

    if order.get("po_number") != "PO-2026-0456":
        errors.append(
            f"Incorrect PO number: {order.get('po_number')}"
        )

    expected_subtotal = 5764.40
    actual_subtotal = order.get("subtotal")

    if (
        not isinstance(actual_subtotal, (int, float))
        or isinstance(actual_subtotal, bool)
        or abs(actual_subtotal - expected_subtotal) > 0.01
    ):
        errors.append(
            f"Subtotal should be {expected_subtotal:.2f}, "
            f"received {actual_subtotal}."
        )

    return errors
expected_items = [
    {
        "item_number": "1896-S",
        "item_description": "ATHENS Desk",
        "quantity": 5,
        "unit_price": 1000.80,
        "line_total": 5004.00,
    },
    {
        "item_number": "1920-S",
        "item_description": "ANTWERP Conference Table",
        "quantity": 10,
        "unit_price": 647.80,
        "line_total": 6478.00,
    },
    {
        "item_number": "1900-S",
        "item_description": "PARIS Guest Chair, black",
        "quantity": 2,
        "unit_price": 192.80,
        "line_total": 385.60,
    },
]

expected_subtotal = 11867.60

# --------------------------------------------------
# STEP 6: MAIN PROGRAM
# --------------------------------------------------

def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH}"
        )

    # Read PDF and extract text using pdf_reader.py.
    pdf_text = extract_pdf_text(PDF_PATH.read_bytes())

    print("PDF text extracted successfully.")

    # Extract the item table deterministically from OCR text.
    items = extract_items_from_text(pdf_text)

    print(f"Item rows extracted directly from OCR: {len(items)}")

    if not items:
        print("No item rows were recognized. Check the OCR output.")
        return

    # Use Ollama for order header information.
    print("Sending order header to Ollama...\n")

    order = extract_order_json(pdf_text)
    order = normalize_order_numbers(order)

    # Use Python-extracted item rows instead of Ollama's item output.
    order["items"] = items

    print("===== EXTRACTED ORDER JSON =====")
    print(json.dumps(order, indent=2))

    # Run both validations.
    errors = validate_order(order)
    errors.extend(validate_against_test_document(order))

    if errors:
        print("\n===== VALIDATION ERRORS =====")

        for error in errors:
            print(f"- {error}")

        print("\nOrder is NOT approved for processing.")
        print("No Business Central order was created.")

    else:
        print("\nAll sample-document validations passed.")
        print("This test does not create a Business Central order.")


if __name__ == "__main__":
    main()

import json
import re
import html
import requests

from bc_client import (
    search_items,
    get_item_details,
    get_inventory,
    search_customers,
    create_customer,
    create_sales_order,
)


# ==========================================================
# OLLAMA CONFIGURATION
# ==========================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2"


# ==========================================================
# PENDING SALES ORDERS
# ==========================================================

pending_orders = {}


# ==========================================================
# CONFIRMATION
# ==========================================================

def is_confirmation(message: str):
    message = message.strip().lower()

    confirmation_words = [
        "yes",
        "yes please",
        "confirm",
        "confirmed",
        "go ahead",
        "go ahead and create it",
        "create it",
        "create the order",
        "please create it",
        "do it",
    ]

    return message in confirmation_words


# ==========================================================
# REJECTION
# ==========================================================

def is_rejection(message: str):
    message = message.strip().lower()

    rejection_words = [
        "no",
        "no thanks",
        "cancel",
        "cancel it",
        "don't create",
        "do not create",
        "stop",
    ]

    return message in rejection_words


# ==========================================================
# SEARCH ITEMS
# ==========================================================

def execute_search_items(search_text: str):

    try:
        items = search_items(search_text)

    except Exception as e:
        return {
            "error": f"Item search failed: {str(e)}"
        }

    if isinstance(items, dict) and items.get("error"):
        return items

    results = []

    for item in items[:10]:
        results.append({
            "item_no": item.get("item_no"),
            "description": item.get("description"),
            "unit_price": item.get("unit_price"),
            "unit_cost": item.get("unit_cost"),
            "inventory": item.get("inventory"),
            "blocked": item.get("blocked"),
        })

    return results


# ==========================================================
# GET ITEM DETAILS
# ==========================================================

def execute_get_item_details(item_no: str):

    try:
        item = get_item_details(item_no)

    except Exception as e:
        return {
            "error": f"Item details lookup failed: {str(e)}"
        }

    if not item:
        return {
            "error": (
                f"Item {item_no} was not found "
                "in Business Central."
            )
        }

    return item


# ==========================================================
# GET INVENTORY
# ==========================================================

def execute_get_inventory(item_no: str):

    try:
        inventory = get_inventory(item_no)

    except Exception as e:
        return {
            "error": f"Inventory lookup failed: {str(e)}"
        }

    if not inventory:
        return {
            "error": (
                f"Inventory information for item "
                f"{item_no} was not found."
            )
        }

    return inventory


# ==========================================================
# SEARCH CUSTOMERS
# ==========================================================

def execute_search_customers(search_text: str):

    try:
        customers = search_customers(search_text)

    except Exception as e:
        return {
            "error": f"Customer search failed: {str(e)}"
        }

    if isinstance(customers, dict) and customers.get("error"):
        return customers

    return customers


# ==========================================================
# CLEAN EMAIL HTML
# ==========================================================

def clean_email_html(email_text: str):
    """
    Convert Outlook HTML email content into clean text.
    """

    if not email_text:
        return ""

    text = html.unescape(email_text)

    # Remove script blocks
    text = re.sub(
        r"<script.*?>.*?</script>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove style blocks
    text = re.sub(
        r"<style.*?>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert common HTML breaks to new lines
    text = re.sub(
        r"<br\s*/?>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"</p\s*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"</div\s*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    # Remove remaining HTML tags
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    # Normalize whitespace
    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n\s*\n+",
        "\n",
        text,
    )

    return text.strip()


# ==========================================================
# EXTRACT JSON FROM AI RESPONSE
# ==========================================================

def parse_ai_json(content: str):
    """
    Safely parse JSON returned by Ollama.
    """

    if not content:
        raise ValueError(
            "Ollama returned an empty response."
        )

    content = content.strip()

    # Remove markdown code fences if present
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE,
    )

    content = re.sub(
        r"\s*```$",
        "",
        content,
    )

    content = content.strip()

    try:
        return json.loads(content)

    except json.JSONDecodeError:

        # Try to find the first JSON object
        start = content.find("{")
        end = content.rfind("}")

        if start >= 0 and end > start:

            possible_json = content[
                start:end + 1
            ]

            return json.loads(possible_json)

        raise


# ==========================================================
# EXTRACT EMAIL ORDER
# ==========================================================

def extract_email_order(email_text):
    """
    Extract customer and order information from an email
    using Ollama /api/generate.

    IMPORTANT:
    /api/generate is used here instead of /api/chat because
    the local Ollama API was returning incomplete responses
    for the chat endpoint.
    """

    # Clean Outlook HTML before sending it to the model
    clean_text = clean_email_html(email_text)

    prompt = f"""
You are an order extraction system for Microsoft Dynamics 365 Business Central.

Read the email below and extract the order information.

Return ONLY valid JSON.

Required JSON structure:

{{
    "customer_name": "",
    "customer_email": "",
    "customer_phone": "",
    "customer_address": "",
    "customer_city": "",
    "customer_state": "",
    "customer_postal_code": "",
    "item_description": "",
    "quantity": 0
}}

Rules:

1. Extract the customer's name.
2. Extract the customer's email.
3. Extract phone number if available.
4. Extract address if available.
5. Extract city if available.
6. Extract state if available.
7. Extract postal code if available.
8. Extract the product/item description.
9. Extract the requested quantity as a number.
10. If a value is not available, use an empty string.
11. Quantity must be a number.
12. Do not add explanations.
13. Do not add markdown.
14. Return ONLY valid JSON.
15. Do not invent information.

EMAIL:

{clean_text}
"""

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    response = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    result = response.json()

    # Ollama /api/generate returns the model output
    content = result.get("response", "").strip()

    if not content:
        raise ValueError(
            "Ollama returned an empty response."
        )

    return parse_ai_json(content)


# ==========================================================
# PROCESS EMAIL ORDER
# ==========================================================

def process_email_order(email_text: str):

    # ======================================================
    # 1. EXTRACT ORDER INFORMATION
    # ======================================================

    try:
        order_data = extract_email_order(email_text)

    except Exception as e:
        print()
        print("EMAIL ORDER EXTRACTION ERROR:")
        print(str(e))
        print()

        return {
            "success": False,
            "message": (
                "AI could not extract the order information."
            ),
            "details": str(e),
        }

    if not isinstance(order_data, dict):
        return {
            "success": False,
            "message": (
                "AI returned invalid order information."
            ),
        }

    print()
    print("EXTRACTED ORDER DATA:")
    print(
        json.dumps(
            order_data,
            indent=2,
            default=str,
        )
    )
    print()

    # ======================================================
    # 2. READ EXTRACTED VALUES
    # ======================================================

    customer_name = str(
        order_data.get(
            "customer_name",
            "",
        )
    ).strip()

    customer_email = str(
        order_data.get(
            "customer_email",
            "",
        )
    ).strip()

    customer_phone = str(
        order_data.get(
            "customer_phone",
            "",
        )
    ).strip()

    customer_address = str(
        order_data.get(
            "customer_address",
            "",
        )
    ).strip()

    customer_city = str(
        order_data.get(
            "customer_city",
            "",
        )
    ).strip()

    customer_state = str(
        order_data.get(
            "customer_state",
            "",
        )
    ).strip()

    customer_postal_code = str(
        order_data.get(
            "customer_postal_code",
            "",
        )
    ).strip()

    # IMPORTANT:
    # The AI extraction field is "item_description".
    # We map it to product_name for the rest of
    # the Business Central workflow.
    product_name = str(
        order_data.get(
            "item_description",
            "",
        )
    ).strip()

    quantity = order_data.get(
        "quantity",
        0,
    )

    # ======================================================
    # 3. CONVERT QUANTITY
    # ======================================================

    try:

        if isinstance(quantity, str):
            quantity = quantity.strip()

            if not quantity:
                quantity = 0

        quantity = int(float(quantity))

    except (ValueError, TypeError):

        return {
            "success": False,
            "message": (
                "The quantity extracted from the email "
                "is not valid."
            ),
            "quantity": quantity,
        }

    # ======================================================
    # 4. VALIDATE REQUIRED INFORMATION
    # ======================================================

    if not customer_name:
        return {
            "success": False,
            "message": (
                "Customer name is missing from the email."
            ),
        }

    if not customer_email:
        return {
            "success": False,
            "message": (
                "Customer email is missing from the email."
            ),
        }

    if not product_name:
        return {
            "success": False,
            "message": (
                "Product name is missing from the email."
            ),
        }

    if quantity <= 0:
        return {
            "success": False,
            "message": (
                "A valid order quantity is required."
            ),
        }

    # ======================================================
    # 5. SEARCH CUSTOMER
    # ======================================================

    print(
        f"Searching customer: {customer_email}"
    )

    customers = execute_search_customers(
        customer_email
    )

    if (
        isinstance(customers, dict)
        and customers.get("error")
    ):
        return {
            "success": False,
            "message": "Customer search failed.",
            "details": customers,
        }

    customer_no = None
    final_customer_name = customer_name
    customer_created = False

    # ======================================================
    # 6. EXISTING CUSTOMER
    # ======================================================

    if customers:

        if len(customers) > 1:
            return {
                "success": False,
                "message": (
                    "Multiple customers were found for "
                    f"email {customer_email}."
                ),
                "customers": customers,
            }

        customer = customers[0]

        customer_no = customer.get(
            "customer_no"
        )

        final_customer_name = (
            customer.get("name")
            or customer_name
        )

        if not customer_no:
            return {
                "success": False,
                "message": (
                    "Customer was found, but Business Central "
                    "did not return a customer number."
                ),
            }

        print(
            f"Existing customer found: {customer_no}"
        )

    # ======================================================
    # 7. CREATE NEW CUSTOMER
    # ======================================================

    else:

        print(
            "Customer not found. Creating new customer."
        )

        customer_result = create_customer(
            name=customer_name,
            email=customer_email,
            phone=customer_phone,
            address=customer_address,
            city=customer_city,
            state=customer_state,
            postal_code=customer_postal_code,
        )

        if not isinstance(
            customer_result,
            dict,
        ):
            return {
                "success": False,
                "message": (
                    "Customer creation returned "
                    "an invalid response."
                ),
            }

        if not customer_result.get(
            "success"
        ):
            return {
                "success": False,
                "message": (
                    "New customer creation failed."
                ),
                "details": customer_result,
            }

        customer_no = customer_result.get(
            "customer_no"
        )

        if not customer_no:
            return {
                "success": False,
                "message": (
                    "Customer was created, but no "
                    "customer number was returned."
                ),
            }

        final_customer_name = customer_name
        customer_created = True

        print(
            f"New customer created: {customer_no}"
        )

    # ======================================================
    # 8. SEARCH PRODUCT
    # ======================================================

    print(
        f"Searching item: {product_name}"
    )

    items = execute_search_items(
        product_name
    )

    if (
        isinstance(items, dict)
        and items.get("error")
    ):
        return {
            "success": False,
            "message": "Product search failed.",
            "customer_no": customer_no,
            "details": items,
        }

    if not items:
        return {
            "success": False,
            "message": (
                f"Product '{product_name}' was not found "
                "in Business Central."
            ),
            "customer_no": customer_no,
        }

    # ======================================================
    # 9. HANDLE MULTIPLE PRODUCTS
    # ======================================================

    if len(items) > 1:

        item_list = []

        for item in items:
            item_list.append({
                "item_no": item.get(
                    "item_no"
                ),
                "description": item.get(
                    "description"
                ),
                "inventory": item.get(
                    "inventory"
                ),
                "unit_price": item.get(
                    "unit_price"
                ),
            })

        return {
            "success": False,
            "message": (
                "Multiple products matched the email "
                "request. Please specify the item."
            ),
            "items": item_list,
            "customer_no": customer_no,
        }

    # ======================================================
    # 10. SELECT ITEM
    # ======================================================

    item = items[0]

    item_no = item.get(
        "item_no"
    )

    item_description = item.get(
        "description"
    )

    unit_price = item.get(
        "unit_price"
    )

    if not item_no:
        return {
            "success": False,
            "message": (
                "The item was found, but Business Central "
                "did not return an item number."
            ),
            "customer_no": customer_no,
        }

    # ======================================================
    # 11. GET FRESH INVENTORY
    # ======================================================

    print(
        f"Checking inventory for: {item_no}"
    )

    inventory_result = execute_get_inventory(
        item_no
    )

    if (
        isinstance(inventory_result, dict)
        and inventory_result.get("error")
    ):
        return {
            "success": False,
            "message": (
                "Inventory validation failed."
            ),
            "customer_no": customer_no,
            "item_no": item_no,
            "details": inventory_result,
        }

    inventory = inventory_result.get(
        "inventory"
    )

    # ======================================================
    # 12. INVENTORY VALIDATION
    # ======================================================

    if inventory is not None:

        try:
            inventory_number = float(
                inventory
            )

        except (ValueError, TypeError):

            return {
                "success": False,
                "message": (
                    "Business Central returned an invalid "
                    "inventory value."
                ),
                "customer_no": customer_no,
                "item_no": item_no,
                "inventory": inventory,
            }

        if quantity > inventory_number:

            return {
                "success": False,
                "message": (
                    f"Requested quantity is {quantity}, "
                    f"but only {inventory_number:g} units "
                    f"are available for "
                    f"{item_description}."
                ),
                "customer_no": customer_no,
                "item_no": item_no,
                "inventory": inventory_number,
            }

    # ======================================================
    # 13. CREATE SALES ORDER
    # ======================================================

    print()
    print("Creating Business Central Sales Order...")
    print(
        f"Customer: {customer_no}"
    )
    print(
        f"Item: {item_no}"
    )
    print(
        f"Quantity: {quantity}"
    )
    print()

    sales_order_result = create_sales_order(
        customer_no=customer_no,
        item_no=item_no,
        quantity=quantity,
    )

    if not isinstance(
        sales_order_result,
        dict,
    ):
        return {
            "success": False,
            "message": (
                "Business Central returned an invalid "
                "Sales Order response."
            ),
            "details": sales_order_result,
        }

    if not sales_order_result.get(
        "success"
    ):
        return {
            "success": False,
            "message": (
                "Sales Order creation failed."
            ),
            "details": sales_order_result,
            "customer_no": customer_no,
            "item_no": item_no,
        }

    # ======================================================
    # 14. SUCCESS
    # ======================================================

    return {
        "success": True,
        "message": (
            "Email order processed successfully."
        ),

        "customer": {
            "customer_no": customer_no,
            "name": final_customer_name,
            "email": customer_email,
            "created": customer_created,
        },

        "item": {
            "item_no": item_no,
            "description": item_description,
            "unit_price": unit_price,
            "inventory_before_order": inventory,
        },

        "quantity": quantity,

        "sales_order": sales_order_result,
    }


# ==========================================================
# PREPARE SALES ORDER
# ==========================================================

def execute_create_sales_order(
    customer_no: str,
    item_no: str,
    quantity: float,
    session_id: str,
):

    pending_orders[session_id] = {
        "customer_no": customer_no,
        "item_no": item_no,
        "quantity": quantity,
    }

    return {
        "status": "confirmation_required",
        "customer_no": customer_no,
        "item_no": item_no,
        "quantity": quantity,
    }


# ==========================================================
# ACTUALLY CREATE SALES ORDER
# ==========================================================

def confirm_and_create_sales_order(
    session_id: str,
):

    pending_order = pending_orders.get(
        session_id
    )

    if not pending_order:
        return {
            "success": False,
            "message": (
                "There is no pending Sales Order "
                "for this session."
            ),
            "details": {},
        }

    print(
        "Creating Sales Order with:",
        pending_order,
    )

    result = create_sales_order(
        customer_no=pending_order[
            "customer_no"
        ],
        item_no=pending_order[
            "item_no"
        ],
        quantity=pending_order[
            "quantity"
        ],
    )

    if (
        isinstance(result, dict)
        and not result.get("success")
    ):
        return {
            "success": False,
            "message": (
                "Sales Order creation failed."
            ),
            "details": result,
        }

    if (
        isinstance(result, dict)
        and result.get("success")
    ):
        pending_orders.pop(
            session_id,
            None,
        )

        return {
            "success": True,
            "message": (
                "Sales Order created successfully."
            ),
            "sales_order_number": result.get(
                "sales_order_number"
            ),
            "customer_no": result.get(
                "customer_no"
            ),
            "item_no": result.get(
                "item_no"
            ),
            "quantity": result.get(
                "quantity"
            ),
            "status": result.get(
                "status"
            ),
            "line_id": result.get(
                "line_id"
            ),
        }

    return {
        "success": False,
        "message": (
            "Unexpected response from Business Central."
        ),
        "details": result,
    }


# ==========================================================
# FORMAT PENDING ORDER
# ==========================================================

def format_pending_order(session_id: str):

    pending = pending_orders.get(
        session_id
    )

    if not pending:
        return (
            "There is no pending Sales Order."
        )

    return (
        "Sales Order is ready for confirmation.\n\n"
        f"Customer No.: "
        f"{pending['customer_no']}\n"
        f"Item No.: "
        f"{pending['item_no']}\n"
        f"Quantity: "
        f"{pending['quantity']}\n\n"
        "Please reply 'Yes' to create the order "
        "or 'No' to cancel it."
    )


# ==========================================================
# EXTRACT QUANTITY
# ==========================================================

def extract_quantity(message: str):

    patterns = [
        r"\bbuy\s+(\d+(?:\.\d+)?)\b",
        r"\border\s+(\d+(?:\.\d+)?)\b",
        r"\bpurchase\s+(\d+(?:\.\d+)?)\b",
        r"\b(\d+(?:\.\d+)?)\s+"
        r"(?:units?|pieces?|pcs?)\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            message,
            re.IGNORECASE,
        )

        if match:

            try:
                return float(
                    match.group(1)
                )

            except ValueError:
                return None

    return None


# ==========================================================
# EXTRACT CUSTOMER
# ==========================================================

def extract_customer_text(message: str):

    # Example:
    # Buy 2 Paris Guest Chairs for customer 10000

    match = re.search(
        r"\bfor\s+customer\s+"
        r"([A-Za-z0-9 .&_\-]+?)"
        r"(?:[.!?,]|$)",
        message,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    # Example:
    # customer 10000

    match = re.search(
        r"\bcustomer\s+"
        r"([A-Za-z0-9 .&_\-]+?)"
        r"(?:[.!?,]|$)",
        message,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


# ==========================================================
# EXTRACT PRODUCT
# ==========================================================

def extract_product_text(message: str):

    match = re.search(
        r"\b(?:buy|order|purchase)\s+"
        r"\d+(?:\.\d+)?\s+"
        r"(.+?)\s+"
        r"(?:for\s+customer|customer)\b",
        message,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


# ==========================================================
# DETERMINISTIC SALES ORDER WORKFLOW
# ==========================================================

def try_prepare_sales_order(
    user_message: str,
    session_id: str,
):

    message = user_message.strip()

    # ------------------------------------------------------
    # Detect order intent
    # ------------------------------------------------------

    order_words = [
        "buy",
        "order",
        "purchase",
    ]

    has_order_intent = any(
        word in message.lower()
        for word in order_words
    )

    if not has_order_intent:
        return None

    # ------------------------------------------------------
    # Extract quantity
    # ------------------------------------------------------

    quantity = extract_quantity(
        message
    )

    if quantity is None:
        return (
            "I can prepare the Sales Order, "
            "but I need the quantity.\n\n"
            "Example: "
            "Buy 2 Paris Guest Chairs "
            "for customer 10000."
        )

    if quantity <= 0:
        return (
            "Quantity must be greater than zero."
        )

    # ------------------------------------------------------
    # Extract customer
    # ------------------------------------------------------

    customer_text = extract_customer_text(
        message
    )

    if not customer_text:
        return (
            "I can prepare the Sales Order, "
            "but I need the customer.\n\n"
            "Example: "
            "Buy 2 Paris Guest Chairs "
            "for customer 10000."
        )

    # ------------------------------------------------------
    # Extract product
    # ------------------------------------------------------

    product_text = extract_product_text(
        message
    )

    if not product_text:
        return (
            "I can prepare the Sales Order, "
            "but I could not identify the product.\n\n"
            "Example: "
            "Buy 2 Paris Guest Chairs "
            "for customer 10000."
        )

    print()
    print("Sales Order Request Detected")
    print(
        "Customer search:",
        customer_text,
    )
    print(
        "Product search:",
        product_text,
    )
    print(
        "Quantity:",
        quantity,
    )
    print()

    # ======================================================
    # SEARCH CUSTOMER
    # ======================================================

    customers = execute_search_customers(
        customer_text
    )

    if (
        isinstance(customers, dict)
        and customers.get("error")
    ):
        return (
            "I could not search the customer "
            "in Business Central.\n\n"
            f"Error: "
            f"{customers.get('error')}"
        )

    if not customers:
        return (
            f"I could not find customer "
            f"'{customer_text}' "
            "in Business Central."
        )

    # ------------------------------------------------------
    # Multiple customers
    # ------------------------------------------------------

    if len(customers) > 1:

        customer_list = "\n".join(
            [
                (
                    f"- {c.get('customer_no')} - "
                    f"{c.get('name')}"
                )
                for c in customers
            ]
        )

        return (
            "I found multiple customers. "
            "Please specify the customer number:\n\n"
            f"{customer_list}"
        )

    # ------------------------------------------------------
    # Customer found
    # ------------------------------------------------------

    customer = customers[0]

    customer_no = customer.get(
        "customer_no"
    )

    customer_name = customer.get(
        "name"
    )

    if not customer_no:
        return (
            "The customer was found, but "
            "Business Central did not return "
            "a customer number."
        )

    # ======================================================
    # SEARCH ITEM
    # ======================================================

    items = execute_search_items(
        product_text
    )

    if (
        isinstance(items, dict)
        and items.get("error")
    ):
        return (
            "I could not search the item "
            "in Business Central.\n\n"
            f"Error: "
            f"{items.get('error')}"
        )

    if not items:
        return (
            f"I could not find "
            f"'{product_text}' "
            "in Business Central."
        )

    # ------------------------------------------------------
    # Multiple items
    # ------------------------------------------------------

    if len(items) > 1:

        item_list = "\n".join(
            [
                (
                    f"- {item.get('item_no')} - "
                    f"{item.get('description')} "
                    f"(Inventory: "
                    f"{item.get('inventory')})"
                )
                for item in items
            ]
        )

        return (
            "I found multiple matching items. "
            "Please specify the item number:\n\n"
            f"{item_list}"
        )

    # ------------------------------------------------------
    # Single item
    # ------------------------------------------------------

    item = items[0]

    item_no = item.get(
        "item_no"
    )

    item_description = item.get(
        "description"
    )

    unit_price = item.get(
        "unit_price"
    )

    if not item_no:
        return (
            "The item was found, but "
            "Business Central did not return "
            "an item number."
        )

    # ======================================================
    # GET FRESH INVENTORY
    # ======================================================

    inventory_result = execute_get_inventory(
        item_no
    )

    if (
        isinstance(inventory_result, dict)
        and inventory_result.get("error")
    ):
        return (
            "I could not check the inventory "
            "in Business Central.\n\n"
            f"Error: "
            f"{inventory_result.get('error')}"
        )

    inventory = inventory_result.get(
        "inventory"
    )

    # ======================================================
    # INVENTORY VALIDATION
    # ======================================================

    if inventory is not None:

        try:
            inventory_number = float(
                inventory
            )

        except (
            ValueError,
            TypeError,
        ):
            return (
                "Business Central returned "
                "an invalid inventory value."
            )

        if quantity > inventory_number:
            return (
                f"The requested quantity is "
                f"{quantity}, but Business Central "
                f"shows only "
                f"{inventory_number:g} units available "
                f"for {item_description}."
            )

    # ======================================================
    # PREPARE PENDING ORDER
    # ======================================================

    execute_create_sales_order(
        customer_no=customer_no,
        item_no=item_no,
        quantity=quantity,
        session_id=session_id,
    )

    # ======================================================
    # CONFIRMATION MESSAGE
    # ======================================================

    return (
        "I found the following information in "
        "Business Central:\n\n"
        f"Customer: {customer_name}\n"
        f"Customer No.: {customer_no}\n\n"
        f"Item: {item_description}\n"
        f"Item No.: {item_no}\n"
        f"Unit Price: {unit_price}\n"
        f"Available Inventory: {inventory}\n"
        f"Quantity: {quantity}\n\n"
        "The Sales Order has NOT been created yet.\n\n"
        "Please reply 'Yes' to create the "
        "Sales Order or 'No' to cancel it."
    )


# ==========================================================
# NORMAL AI CHAT
# ==========================================================

def ask_normal_ai(user_message: str):

    tools = [

        {
            "type": "function",
            "function": {
                "name": "search_items",
                "description": (
                    "Search products and inventory "
                    "items in Business Central."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_text": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "search_text"
                    ],
                },
            },
        },

        {
            "type": "function",
            "function": {
                "name": "get_item_details",
                "description": (
                    "Get detailed information "
                    "about a Business Central item."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_no": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "item_no"
                    ],
                },
            },
        },

        {
            "type": "function",
            "function": {
                "name": "get_inventory",
                "description": (
                    "Get current inventory "
                    "for a Business Central item."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_no": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "item_no"
                    ],
                },
            },
        },

        {
            "type": "function",
            "function": {
                "name": "search_customers",
                "description": (
                    "Search customers "
                    "in Business Central."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_text": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "search_text"
                    ],
                },
            },
        },
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI sales assistant "
                "connected to Microsoft Dynamics "
                "365 Business Central.\n\n"
                "Business Central is the source "
                "of truth.\n\n"
                "Never invent Business Central data.\n\n"
                "For product questions, use "
                "search_items or "
                "get_item_details.\n\n"
                "For inventory questions, use "
                "get_inventory.\n\n"
                "For customer questions, use "
                "search_customers.\n\n"
                "Give concise answers based only "
                "on Business Central results."
            ),
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    assistant_message = response.json()[
        "message"
    ]

    # ------------------------------------------------------
    # No tool call
    # ------------------------------------------------------

    if not assistant_message.get(
        "tool_calls"
    ):
        return assistant_message.get(
            "content",
            "I could not generate a response.",
        )

    messages.append(
        assistant_message
    )

    # ======================================================
    # TOOL LOOP
    # ======================================================

    max_tool_rounds = 5

    for _ in range(max_tool_rounds):

        tool_calls = assistant_message.get(
            "tool_calls",
            [],
        )

        if not tool_calls:
            return assistant_message.get(
                "content",
                "I could not generate a response.",
            )

        for tool_call in tool_calls:

            function_name = (
                tool_call[
                    "function"
                ]["name"]
            )

            arguments = (
                tool_call[
                    "function"
                ].get(
                    "arguments",
                    {},
                )
            )

            if isinstance(
                arguments,
                str,
            ):

                try:
                    arguments = json.loads(
                        arguments
                    )

                except json.JSONDecodeError:
                    arguments = {}

            # ----------------------------------------------
            # Search Items
            # ----------------------------------------------

            if function_name == "search_items":

                search_text = arguments.get(
                    "search_text",
                    "",
                )

                result = execute_search_items(
                    search_text
                )

            # ----------------------------------------------
            # Item Details
            # ----------------------------------------------

            elif function_name == "get_item_details":

                item_no = arguments.get(
                    "item_no",
                    "",
                )

                result = execute_get_item_details(
                    item_no
                )

            # ----------------------------------------------
            # Inventory
            # ----------------------------------------------

            elif function_name == "get_inventory":

                item_no = arguments.get(
                    "item_no",
                    "",
                )

                result = execute_get_inventory(
                    item_no
                )

            # ----------------------------------------------
            # Search Customers
            # ----------------------------------------------

            elif function_name == "search_customers":

                search_text = arguments.get(
                    "search_text",
                    "",
                )

                result = execute_search_customers(
                    search_text
                )

            # ----------------------------------------------
            # Unknown Tool
            # ----------------------------------------------

            else:

                result = {
                    "error": (
                        f"Unknown tool: "
                        f"{function_name}"
                    )
                }

            # ----------------------------------------------
            # Add Tool Result
            # ----------------------------------------------

            messages.append({
                "role": "tool",
                "content": json.dumps(
                    result,
                    default=str,
                ),
            })

        # --------------------------------------------------
        # Ask Ollama again
        # --------------------------------------------------

        next_payload = {
            "model": MODEL,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }

        next_response = requests.post(
            OLLAMA_URL,
            json=next_payload,
            timeout=120,
        )

        next_response.raise_for_status()

        assistant_message = (
            next_response.json()[
                "message"
            ]
        )

        # --------------------------------------------------
        # Final answer
        # --------------------------------------------------

        if not assistant_message.get(
            "tool_calls"
        ):
            return assistant_message.get(
                "content",
                "I could not generate a response.",
            )

        messages.append(
            assistant_message
        )

    return (
        "I could not complete the Business Central "
        "lookup within the allowed tool steps."
    )


# ==========================================================
# MAIN AGENT
# ==========================================================

def ask_agent(
    user_message: str,
    session_id: str = "default",
):

    # ======================================================
    # EXISTING PENDING ORDER
    # ======================================================

    if session_id in pending_orders:

        # --------------------------------------------------
        # YES
        # --------------------------------------------------

        if is_confirmation(
            user_message
        ):

            result = confirm_and_create_sales_order(
                session_id
            )

            if result.get("success"):

                return (
                    "Sales Order created successfully.\n\n"
                    f"Sales Order No.: "
                    f"{result.get('sales_order_number')}\n"
                    f"Customer No.: "
                    f"{result.get('customer_no')}\n"
                    f"Item No.: "
                    f"{result.get('item_no')}\n"
                    f"Quantity: "
                    f"{result.get('quantity')}\n"
                    f"Status: "
                    f"{result.get('status')}"
                )

            return (
                "I could not create the Sales Order.\n\n"
                f"Reason: "
                f"{result.get('message')}\n\n"
                f"Details:\n"
                f"{json.dumps(
                    result.get('details'),
                    indent=2,
                    default=str
                )}"
            )

        # --------------------------------------------------
        # NO
        # --------------------------------------------------

        if is_rejection(
            user_message
        ):

            pending_orders.pop(
                session_id,
                None,
            )

            return (
                "The Sales Order request "
                "has been cancelled."
            )

        # --------------------------------------------------
        # Other response
        # --------------------------------------------------

        return format_pending_order(
            session_id
        )

    # ======================================================
    # DETERMINISTIC SALES ORDER FLOW
    # ======================================================

    sales_order_response = (
        try_prepare_sales_order(
            user_message,
            session_id,
        )
    )

    if sales_order_response is not None:
        return sales_order_response

    # ======================================================
    # NORMAL AI CHAT
    # ======================================================

    return ask_normal_ai(
        user_message
    )
import os
import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Load Environment Variables
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_FILE, override=True)


# --------------------------------------------------
# Business Central Configuration
# --------------------------------------------------

TENANT_ID = os.getenv("BC_TENANT_ID")
CLIENT_ID = os.getenv("BC_CLIENT_ID")
CLIENT_SECRET = os.getenv("BC_CLIENT_SECRET")
BC_ENVIRONMENT = os.getenv("BC_ENVIRONMENT")
BC_COMPANY = os.getenv("BC_COMPANY")

BC_BASE_URL = "https://api.businesscentral.dynamics.com"


# --------------------------------------------------
# OAuth Configuration
# --------------------------------------------------

TOKEN_URL = (
    f"https://login.microsoftonline.com/"
    f"{TENANT_ID}/oauth2/v2.0/token"
)

SCOPE = f"{BC_BASE_URL}/.default"


# --------------------------------------------------
# Get Business Central Access Token
# --------------------------------------------------

def get_access_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": SCOPE
    }

    response = requests.post(
        TOKEN_URL,
        data=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()["access_token"]


# --------------------------------------------------
# Get Business Central Company ID
# --------------------------------------------------

def get_company_id():
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    companies_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/companies"
    )

    response = requests.get(
        companies_url,
        headers=headers,
        timeout=60
    )

    response.raise_for_status()
    companies = response.json().get("value", [])

    for company in companies:
        if (
            company.get("displayName") == BC_COMPANY
            or company.get("name") == BC_COMPANY
        ):
            return company.get("id")

    return None


# --------------------------------------------------
# Get All Items
# --------------------------------------------------

def get_items():
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    items_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/items"
    )

    response = requests.get(
        items_url,
        headers=headers,
        timeout=60
    )

    response.raise_for_status()
    return response.json()


# --------------------------------------------------
# Search Items
# --------------------------------------------------

def search_items(search_text: str):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    items_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/items"
    )

    response = requests.get(
        items_url,
        headers=headers,
        timeout=60
    )

    response.raise_for_status()
    all_items = response.json().get("value", [])

    search_text = search_text.strip().lower()
    search_words = search_text.split()

    normalized_words = []

    for word in search_words:
        if len(word) > 3 and word.endswith("s"):
            word = word[:-1]

        normalized_words.append(word)

    matching_items = []

    for item in all_items:
        description = (
            item.get("displayName") or ""
        ).lower()

        item_number = (
            item.get("number") or ""
        ).lower()

        if all(
            word in description or word in item_number
            for word in normalized_words
        ):
            matching_items.append({
                "item_no": item.get("number"),
                "description": item.get("displayName"),
                "inventory": item.get("inventory"),
                "unit_price": item.get("unitPrice"),
                "unit_cost": item.get("unitCost"),
                "blocked": item.get("blocked")
            })

    return matching_items[:10]


# --------------------------------------------------
# Get Item Details
# --------------------------------------------------

def get_item_details(item_no: str):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    items_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/items"
    )

    item_no = item_no.replace("'", "''")

    params = {
        "$filter": f"number eq '{item_no}'"
    }

    response = requests.get(
        items_url,
        headers=headers,
        params=params,
        timeout=60
    )

    response.raise_for_status()
    items = response.json().get("value", [])

    if not items:
        return None

    item = items[0]

    return {
        "item_no": item.get("number"),
        "description": item.get("displayName"),
        "unit_price": item.get("unitPrice"),
        "unit_cost": item.get("unitCost"),
        "inventory": item.get("inventory"),
        "blocked": item.get("blocked")
    }


# --------------------------------------------------
# Get Item Inventory
# --------------------------------------------------

def get_inventory(item_no: str):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    items_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/items"
    )

    item_no = item_no.replace("'", "''")

    params = {
        "$filter": f"number eq '{item_no}'"
    }

    response = requests.get(
        items_url,
        headers=headers,
        params=params,
        timeout=60
    )

    response.raise_for_status()
    items = response.json().get("value", [])

    if not items:
        return None

    item = items[0]

    return {
        "item_no": item.get("number"),
        "description": item.get("displayName"),
        "inventory": item.get("inventory"),
        "blocked": item.get("blocked")
    }


# --------------------------------------------------
# Normalize Customer Blocked Value
# --------------------------------------------------

def normalize_customer_blocked(value):
    """Normalize the Blocked field returned by Business Central."""

    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in ("", "_x0020_", "false"):
            return False

        if normalized == "true":
            return True

        return normalized

    return None


# --------------------------------------------------
# Get All Customers (read-only, supports BC pagination)
# --------------------------------------------------

def get_all_customers():
    """Return customer records from Business Central, following nextLink."""
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    company_id = get_company_id()
    if not company_id:
        raise RuntimeError(f"Company '{BC_COMPANY}' was not found.")

    url = (
        f"{BC_BASE_URL}/v2.0/{TENANT_ID}/{BC_ENVIRONMENT}/"
        f"api/v2.0/companies({company_id})/customers"
    )

    customers = []
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        payload = response.json()
        customers.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")

    return [
        {
            "customer_no": customer.get("number"),
            "name": customer.get("displayName"),
            "address": customer.get("addressLine1"),
            "city": customer.get("city"),
            "state": customer.get("state"),
            "post_code": customer.get("postalCode"),
            "country": customer.get("country"),
            "phone": customer.get("phoneNumber"),
            "email": customer.get("email"),
            "blocked": normalize_customer_blocked(customer.get("blocked")),
        }
        for customer in customers
    ]


# --------------------------------------------------
# Search Customers
# --------------------------------------------------


from matching_engine import compare_text


def search_customers(search_text: str):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        raise RuntimeError(
            f"Company '{BC_COMPANY}' was not found."
        )

    customers_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/customers"
    )

    # Retrieve customer records, including additional pages.
    all_customers = []
    next_url = customers_url

    while next_url:
        response = requests.get(
            next_url,
            headers=headers,
            params={"$top": 1000} if next_url == customers_url else None,
            timeout=60
        )

        response.raise_for_status()
        data = response.json()

        all_customers.extend(data.get("value", []))
        next_url = data.get("@odata.nextLink")

    search_text = search_text.strip()

    if not search_text:
        return []

    matching_customers = []

    for customer in all_customers:
        name = customer.get("displayName") or ""
        number = customer.get("number") or ""
        email = customer.get("email") or ""

        # Compare the search value with the customer name.
        name_comparison = compare_text(search_text, name)

        # Exact matching for customer number and email.
        email_matches = (
            search_text.casefold() == email.strip().casefold()
        )

        number_matches = (
            search_text.casefold() == number.strip().casefold()
        )

        score = name_comparison["score"]

        if email_matches or number_matches:
            match_type = "EXACT_IDENTIFIER"
        elif score >= 85:
            match_type = "NAME_SIMILARITY"
        else:
            continue

        matching_customers.append({
            "customer_no": number,
            "name": name,
            "address": customer.get("addressLine1"),
            "city": customer.get("city"),
            "state": customer.get("state"),
            "post_code": customer.get("postalCode"),
            "country": customer.get("country"),
            "phone": customer.get("phoneNumber"),
            "email": email,
            "blocked": normalize_customer_blocked(
                customer.get("blocked")
            ),
            "name_similarity": score,
            "match_type": match_type
        })

    matching_customers.sort(
        key=lambda customer: (
            customer["match_type"] == "EXACT_IDENTIFIER",
            customer["name_similarity"]
        ),
        reverse=True
    )

    return matching_customers[:10]


# --------------------------------------------------
# Create Customer
# Using Custom AI Customer API
# --------------------------------------------------

def create_customer(
    name: str,
    email: str = "",
    phone: str = "",
    address: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    country: str = ""
):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "success": False,
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    customers_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/aibc/agent/v1.0/"
        f"companies({company_id})/customers"
    )

    customer_data = {
        "displayName": name,
        "email": email,
        "phoneNumber": phone,
        "addressLine1": address,
        "city": city,
        "state": state,
        "postalCode": postal_code,
        "genBusPostingGroup": "DOMESTIC",
        "customerPostingGroup": "DOMESTIC"
    }

    if country:
        customer_data["country"] = country

    response = requests.post(
        customers_url,
        headers=headers,
        json=customer_data,
        timeout=60
    )

    if not response.ok:
        return {
            "success": False,
            "status_code": response.status_code,
            "error": response.text
        }

    customer = response.json()

    return {
        "success": True,
        "customer_no": customer.get("number"),
        "customer_id": customer.get("id"),
        "name": customer.get("displayName"),
        "email": customer.get("email"),
        "phone": customer.get("phoneNumber"),
        "address": customer.get("addressLine1"),
        "city": customer.get("city"),
        "state": customer.get("state"),
        "postal_code": customer.get("postalCode"),
        "country": customer.get("country"),
        "gen_bus_posting_group": customer.get(
            "genBusPostingGroup"
        ),
        "customer_posting_group": customer.get(
            "customerPostingGroup"
        )
    }


# --------------------------------------------------
# Create Sales Order - Single Item
# --------------------------------------------------

def create_sales_order(
    customer_no: str,
    item_no: str,
    quantity: int
):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    sales_orders_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/salesOrders"
    )

    order_data = {
        "customerNumber": customer_no
    }

    response = requests.post(
        sales_orders_url,
        headers=headers,
        json=order_data,
        timeout=60
    )

    if not response.ok:
        return {
            "error": "Sales Order creation failed.",
            "status_code": response.status_code,
            "business_central_response": response.text
        }

    sales_order = response.json()
    sales_order_id = sales_order.get("id")
    sales_order_number = sales_order.get("number")

    if not sales_order_id:
        return {
            "error": (
                "Business Central created the Sales Order "
                "but did not return an order ID."
            ),
            "response": sales_order
        }

    lines_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/"
        f"{BC_ENVIRONMENT}/"
        f"api/v2.0/"
        f"companies({company_id})/"
        f"salesOrders({sales_order_id})/"
        f"salesOrderLines"
    )

    line_data = {
        "lineType": "Item",
        "lineObjectNumber": item_no,
        "quantity": quantity
    }

    response = requests.post(
        lines_url,
        headers=headers,
        json=line_data,
        timeout=60
    )

    if not response.ok:
        return {
            "error": "Sales Order line creation failed.",
            "status_code": response.status_code,
            "business_central_response": response.text,
            "sales_order_number": sales_order_number,
            "sales_order_id": sales_order_id
        }

    sales_order_line = response.json()

    return {
        "success": True,
        "sales_order_number": sales_order_number,
        "customer_no": customer_no,
        "item_no": item_no,
        "quantity": quantity,
        "status": sales_order.get("status"),
        "sales_order_id": sales_order_id,
        "line_id": sales_order_line.get("id")
    }


# --------------------------------------------------
# Create Sales Order with Multiple Item Lines
# --------------------------------------------------

def create_sales_order_multi_line(
    customer_no: str,
    order_lines: list[dict]
):
    """
    Create a Business Central Sales Order with multiple item lines.

    Example:
        order_lines = [
            {"item_no": "ITEM001", "quantity": 2},
            {"item_no": "ITEM002", "quantity": 3}
        ]

    WARNING:
    This creates real records in Business Central.
    Test in a sandbox first. If a line fails, the order header
    and previously created lines may remain in Business Central.
    """

    if not customer_no or not customer_no.strip():
        return {
            "success": False,
            "error": "Customer number is required."
        }

    if not order_lines:
        return {
            "success": False,
            "error": "At least one order line is required."
        }

    # Validate every line before creating the order.
    for index, line in enumerate(order_lines, start=1):
        if not isinstance(line, dict):
            return {
                "success": False,
                "error": f"Order line {index} must be an object."
            }

        item_no = str(line.get("item_no") or "").strip()
        quantity = line.get("quantity")

        if not item_no:
            return {
                "success": False,
                "error": f"Item number is missing on line {index}."
            }

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
        ):
            return {
                "success": False,
                "error": f"Quantity must be numeric on line {index}."
            }

        if quantity <= 0:
            return {
                "success": False,
                "error": (
                    f"Quantity must be greater than zero "
                    f"on line {index}."
                )
            }

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    company_id = get_company_id()

    if not company_id:
        return {
            "success": False,
            "error": f"Company '{BC_COMPANY}' was not found."
        }

    base_url = (
        f"{BC_BASE_URL}/v2.0/"
        f"{TENANT_ID}/{BC_ENVIRONMENT}/"
        f"api/v2.0/companies({company_id})"
    )

    # 1. Create the Sales Order header.
    try:
        response = requests.post(
            f"{base_url}/salesOrders",
            headers=headers,
            json={"customerNumber": customer_no.strip()},
            timeout=60
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "step": "create_header",
            "error": str(exc),
            "warning": (
                "Check Business Central before retrying, "
                "to avoid creating a duplicate order."
            )
        }

    if not response.ok:
        return {
            "success": False,
            "step": "create_header",
            "status_code": response.status_code,
            "error": response.text
        }

    sales_order = response.json()
    sales_order_id = sales_order.get("id")
    sales_order_number = sales_order.get("number")

    if not sales_order_id:
        return {
            "success": False,
            "step": "read_header",
            "error": (
                "Business Central did not return "
                "the Sales Order ID."
            ),
            "response": sales_order
        }

    # 2. Add each item line.
    lines_url = (
        f"{base_url}/salesOrders({sales_order_id})/"
        f"salesOrderLines"
    )

    created_lines = []

    for index, line in enumerate(order_lines, start=1):
        item_no = str(line["item_no"]).strip()

        line_data = {
            "lineType": "Item",
            "lineObjectNumber": item_no,
            "quantity": line["quantity"]
        }

        try:
            line_response = requests.post(
                lines_url,
                headers=headers,
                json=line_data,
                timeout=60
            )
        except requests.RequestException as exc:
            return {
                "success": False,
                "step": "create_line",
                "failed_line": index,
                "error": str(exc),
                "sales_order_number": sales_order_number,
                "sales_order_id": sales_order_id,
                "created_lines": created_lines,
                "warning": (
                    "The order may be partially created. "
                    "Check Business Central before retrying."
                )
            }

        if not line_response.ok:
            return {
                "success": False,
                "step": "create_line",
                "failed_line": index,
                "status_code": line_response.status_code,
                "error": line_response.text,
                "sales_order_number": sales_order_number,
                "sales_order_id": sales_order_id,
                "created_lines": created_lines,
                "warning": (
                    "The order may be partially created. "
                    "Check Business Central before retrying."
                )
            }

        created_line = line_response.json()

        created_lines.append({
            "item_no": item_no,
            "quantity": line["quantity"],
            "line_id": created_line.get("id")
        })

    return {
        "success": True,
        "sales_order_number": sales_order_number,
        "sales_order_id": sales_order_id,
        "customer_no": customer_no.strip(),
        "lines_created": len(created_lines),
        "created_lines": created_lines,
        "status": sales_order.get("status")
    }
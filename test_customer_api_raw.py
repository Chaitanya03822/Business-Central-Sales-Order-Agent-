
import requests
from bc_client import (
    get_access_token,
    get_company_id,
    BC_BASE_URL,
    TENANT_ID,
    BC_ENVIRONMENT,
)

token = get_access_token()
company_id = get_company_id()

if not company_id:
    raise RuntimeError("Business Central company was not found.")

url = (
    f"{BC_BASE_URL}/v2.0/"
    f"{TENANT_ID}/"
    f"{BC_ENVIRONMENT}/"
    f"api/v2.0/"
    f"companies({company_id})/customers"
)

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
}

response = requests.get(
    url,
    headers=headers,
    params={
        "$filter": "number eq 'C00090'",
        "$select": "number,displayName,email,blocked",
    },
    timeout=60,
)

response.raise_for_status()
data = response.json()

print("HTTP status:", response.status_code)
print("Raw customer response:")

for customer in data.get("value", []):
    print({
        "number": customer.get("number"),
        "displayName": customer.get("displayName"),
        "email": customer.get("email"),
        "blocked": customer.get("blocked"),
    })

if not data.get("value"):
    print("No customer returned. Check the filter and API response.")

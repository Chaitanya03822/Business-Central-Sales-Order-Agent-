
from bc_client import search_customers
import json


def validate_customer(email: str) -> dict:
    """
    Validate a customer using the email extracted from a PDF.

    This function only validates customer information.
    It does not create customers or sales orders.
    """

    email = email.strip().lower()

    # Step 1: Validate the input email.
    if not email:
        return {
            "status": "MANUAL_REVIEW",
            "reason": "Customer email is missing.",
            "customer": None,
        }

    # Step 2: Search for customers in Business Central.
    customers = search_customers(email)

    # Step 3: Require an exact email match.
    exact_matches = [
        customer
        for customer in customers
        if (customer.get("email") or "").strip().lower() == email
    ]

    # Step 4: Handle duplicate email matches.
    if len(exact_matches) > 1:
        return {
            "status": "MANUAL_REVIEW",
            "reason": "Multiple customers have the same email.",
            "customer": None,
        }

    # Step 5: Handle an email that was not found.
    if len(exact_matches) == 0:
        return {
            "status": "NOT_FOUND",
            "reason": "No exact customer email match was found.",
            "customer": None,
        }

    # Step 6: Validate the single matching customer.
    customer = exact_matches[0]
    blocked_value = customer.get("blocked")

    # A confirmed blocked value must stop the workflow.
    if blocked_value is True:
        return {
            "status": "MANUAL_REVIEW",
            "reason": "The matched customer is blocked.",
            "customer": customer,
        }

    # Only a confirmed Boolean False is accepted as unblocked.
    if blocked_value is not False:
        return {
            "status": "MANUAL_REVIEW",
            "reason": (
                "Customer blocked status could not be verified "
                f"from the API. Returned value: {blocked_value!r}"
            ),
            "customer": customer,
        }

    # Step 7: Customer email and blocked status are verified.
    return {
        "status": "MATCHED",
        "reason": (
            "One exact email match was found and the customer "
            "is confirmed as unblocked."
        ),
        "customer": customer,
    }


if __name__ == "__main__":
    print("=" * 55)
    print("BUSINESS CENTRAL CUSTOMER VALIDATION")
    print("VALIDATION ONLY - NO ORDER CREATION")
    print("=" * 55)

    test_email = input(
        "Enter customer email from the test PDF: "
    ).strip()

    try:
        result = validate_customer(test_email)

        print("\n===== CUSTOMER VALIDATION RESULT =====")
        print(json.dumps(result, indent=2, default=str))

        print("\n===== FINAL STATUS =====")
        print(result["status"])
        print(result["reason"])

        print("\nNo Business Central sales order was created.")

    except Exception as error:
        print("\nCustomer validation failed.")
        print(f"Error: {error}")
        print("No Business Central sales order was created.")

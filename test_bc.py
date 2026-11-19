from bc_client import create_sales_order


try:

    customer_no = "10000"
    item_no = "1900-S"
    quantity = 2

    print("Creating Sales Order...")
    print("-" * 60)

    result = create_sales_order(
        customer_no=customer_no,
        item_no=item_no,
        quantity=quantity
    )

    print("\nSUCCESS - Sales Order created")
    print("-" * 60)

    print("Sales Order No.:", result.get("sales_order_no"))
    print("Customer No.:", result.get("customer_no"))
    print("Item No.:", result.get("item_no"))
    print("Quantity:", result.get("quantity"))
    print("Status:", result.get("status"))
    print("Line ID:", result.get("line_id"))

except Exception as e:

    print("\nERROR:")
    print(e)
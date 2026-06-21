import json

def lambda_handler(event, context):
    """Validate order has required fields and valid values."""
    order = event.get("order", {})
    
    errors = []
    if not order.get("customerId"):
        errors.append("customerId is required")
    if not order.get("items") or len(order.get("items", [])) == 0:
        errors.append("At least one item is required")
    if not order.get("shippingAddress"):
        errors.append("shippingAddress is required")
    
    # Validate items
    for i, item in enumerate(order.get("items", [])):
        if not item.get("productId"):
            errors.append(f"Item {i+1}: productId required")
        if not item.get("quantity") or item.get("quantity", 0) <= 0:
            errors.append(f"Item {i+1}: quantity must be positive")
        if not item.get("price") or item.get("price", 0) <= 0:
            errors.append(f"Item {i+1}: price must be positive")
    
    if errors:
        return {
            "valid": False,
            "errors": errors,
            "order": order
        }
    
    # Calculate total
    total = sum(item["price"] * item["quantity"] for item in order["items"])
    
    return {
        "valid": True,
        "order": order,
        "orderTotal": total
    }

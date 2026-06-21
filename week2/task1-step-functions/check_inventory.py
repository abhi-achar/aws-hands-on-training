import json

# Simulated inventory database
INVENTORY = {
    "PROD-001": {"name": "Wireless Headphones", "stock": 50},
    "PROD-002": {"name": "Phone Case", "stock": 200},
    "PROD-003": {"name": "USB-C Cable", "stock": 0},  # Out of stock!
    "PROD-004": {"name": "Laptop Stand", "stock": 15},
}

def lambda_handler(event, context):
    """Check if all items are in stock."""
    order = event.get("order", {})
    items = order.get("items", [])
    
    out_of_stock = []
    inventory_result = []
    
    for item in items:
        product_id = item["productId"]
        requested_qty = item["quantity"]
        product = INVENTORY.get(product_id)
        
        if not product:
            out_of_stock.append({
                "productId": product_id,
                "reason": "Product not found"
            })
        elif product["stock"] < requested_qty:
            out_of_stock.append({
                "productId": product_id,
                "name": product["name"],
                "available": product["stock"],
                "requested": requested_qty
            })
        else:
            inventory_result.append({
                "productId": product_id,
                "name": product["name"],
                "reserved": requested_qty
            })
    
    return {
        "inStock": len(out_of_stock) == 0,
        "outOfStock": out_of_stock,
        "reserved": inventory_result,
        "order": order,
        "orderTotal": event.get("orderTotal", 0)
    }

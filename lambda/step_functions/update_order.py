import os
import uuid
import boto3
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    """Save final order to DynamoDB."""
    order = event.get("order", {})
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    item = {
        "orderId": order_id,
        "customerId": order["customerId"],
        "items": order["items"],
        "shippingAddress": order["shippingAddress"],
        "orderTotal": Decimal(str(event.get("orderTotal", 0))),
        "paymentId": event.get("paymentId", "N/A"),
        "status": "CONFIRMED",
        "createdAt": datetime.utcnow().isoformat(),
    }

    table.put_item(Item=item)

    return {
        "orderId": order_id,
        "status": "CONFIRMED",
        "customerId": order["customerId"],
        "orderTotal": event.get("orderTotal", 0),
        "paymentId": event.get("paymentId", "N/A"),
    }

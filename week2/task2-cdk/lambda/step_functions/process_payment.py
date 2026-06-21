import uuid
import random


def lambda_handler(event, context):
    """Simulate payment processing. Fails for customerIds ending in FAIL."""
    order = event.get("order", {})
    order_total = event.get("orderTotal", 0)

    # Force failure for demo: customerId ending in "FAIL"
    if order.get("customerId", "").endswith("FAIL"):
        raise Exception("Payment gateway timeout - please retry")

    # Random failure ~10% of the time
    if random.random() < 0.1:
        raise Exception("Payment service temporarily unavailable")

    payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"

    return {
        "paymentSuccess": True,
        "paymentId": payment_id,
        "amountCharged": order_total,
        "currency": "INR",
        "order": order,
        "orderTotal": order_total
    }

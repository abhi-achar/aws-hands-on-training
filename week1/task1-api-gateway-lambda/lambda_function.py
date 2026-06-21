import json


def lambda_handler(event, context):
    """Handle API Gateway requests."""
    http_method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    if path == "/health":
        body = {"status": "healthy", "service": "training-api"}
    elif path == "/actions" and http_method == "GET":
        body = {"actions": [], "message": "Actions endpoint"}
    elif path == "/actions" and http_method == "POST":
        request_body = json.loads(event.get("body", "{}"))
        body = {"created": True, "data": request_body}
    else:
        body = {"message": "Welcome to AWS Training API"}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body)
    }

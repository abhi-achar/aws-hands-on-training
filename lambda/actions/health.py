"""
Lambda handler for the health check endpoint (GET /).
"""

import json


def handler(event, context):
    """Simple health check - replaces FastAPI root endpoint."""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"status": "running", "service": "scj-sales-coach"}),
    }

"""
Order API - integrates Step Functions orchestration into a serverless API.

Routes (API Gateway proxy integration):
  POST /orders            -> starts an execution of OrderProcessingWorkflow-CDK
  GET  /orders/{id}       -> returns the status/output of an execution

This Lambda is the bridge between a simple synchronous serverless API and the
existing asynchronous Step Functions orchestration.
"""

import json
import os
import uuid

import boto3

sfn = boto3.client("stepfunctions")
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _start_execution(event):
    """Start a new orchestration run from an incoming order."""
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Request body must be valid JSON"})

    order = payload.get("order")
    if not order:
        return _response(400, {"error": "Missing 'order' in request body"})

    name = f"api-{uuid.uuid4().hex[:12]}"
    result = sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=name,
        input=json.dumps({"order": order}),
    )

    execution_id = result["executionArn"].split(":")[-1]
    return _response(202, {
        "message": "Order accepted and orchestration started",
        "executionId": execution_id,
        "executionArn": result["executionArn"],
        "statusUrl": f"/orders/{execution_id}",
    })


def _get_status(execution_id):
    """Return the current status/output of an orchestration run."""
    region = STATE_MACHINE_ARN.split(":")[3]
    account = STATE_MACHINE_ARN.split(":")[4]
    execution_arn = (
        f"arn:aws:states:{region}:{account}:execution:"
        f"OrderProcessingWorkflow-CDK:{execution_id}"
    )

    try:
        result = sfn.describe_execution(executionArn=execution_arn)
    except sfn.exceptions.ExecutionDoesNotExist:
        return _response(404, {"error": f"Execution '{execution_id}' not found"})

    body = {
        "executionId": execution_id,
        "status": result["status"],
        "startDate": result["startDate"].isoformat(),
    }
    if result.get("output"):
        body["output"] = json.loads(result["output"])
    if result.get("stopDate"):
        body["stopDate"] = result["stopDate"].isoformat()
    return _response(200, body)


def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}

    if method == "POST":
        return _start_execution(event)

    if method == "GET" and path_params.get("id"):
        return _get_status(path_params["id"])

    return _response(400, {"error": "Unsupported route"})

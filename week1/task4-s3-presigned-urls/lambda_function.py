import json
import os
import uuid
from datetime import datetime

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET = os.environ["BUCKET_NAME"]
TABLE = os.environ["TABLE_NAME"]
table = dynamodb.Table(TABLE)


def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "")
    params = event.get("queryStringParameters") or {}

    # Parse the request body defensively: an empty body is fine, but malformed
    # JSON must return a clean 400 instead of crashing the function (502).
    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            return respond(400, {"error": "Request body is not valid JSON"})

    try:
        # POST /docs/upload → Get upload URL + save metadata
        if method == "POST" and "/upload" in path:
            return handle_upload(body)

        # GET /docs/download?employeeId=E001&documentId=xxx → Get download URL
        elif method == "GET" and "/download" in path:
            return handle_download(params)

        # GET /docs?employeeId=E001 → List all docs for an employee
        elif method == "GET" and "/docs" in path:
            return handle_list(params)

        else:
            return respond(400, {"error": "Invalid route"})

    except Exception as e:
        print(f"[Error] {e}")
        return respond(500, {"error": str(e)})


def handle_upload(body):
    """
    Employee requests an upload URL.
    Input: {"employeeId": "E001", "employeeName": "Abhishek", "docType": "id_proof", "fileName": "aadhaar.pdf"}
    """
    employee_id = body.get("employeeId")
    employee_name = body.get("employeeName", "Unknown")
    doc_type = body.get("docType")  # id_proof, resume, certificate
    file_name = body.get("fileName")

    if not all([employee_id, doc_type, file_name]):
        return respond(400, {"error": "employeeId, docType, and fileName are required"})

    # Generate unique document ID
    doc_id = f"{doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # S3 key: organized by employee/docType/file
    s3_key = f"{employee_id}/{doc_type}/{file_name}"

    # Generate pre-signed upload URL (valid 10 minutes)
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": s3_key},
        ExpiresIn=600,
    )

    # Save metadata to DynamoDB
    table.put_item(Item={
        "employeeId": employee_id,
        "documentId": doc_id,
        "employeeName": employee_name,
        "docType": doc_type,
        "fileName": file_name,
        "s3Key": s3_key,
        "uploadedAt": datetime.now().isoformat(),
        "status": "pending_upload",
    })

    return respond(200, {
        "message": f"Upload URL generated for {file_name}",
        "uploadUrl": upload_url,
        "documentId": doc_id,
        "s3Key": s3_key,
        "instructions": "PUT the file to uploadUrl with the file as the request body",
        "expiresIn": "10 minutes",
    })


def handle_download(params):
    """
    Get a temporary download link for a document.
    Query: ?employeeId=E001&documentId=id_proof_20260614_abc123
    """
    employee_id = params.get("employeeId")
    document_id = params.get("documentId")

    if not all([employee_id, document_id]):
        return respond(400, {"error": "employeeId and documentId are required"})

    # Get metadata from DynamoDB
    response = table.get_item(Key={
        "employeeId": employee_id,
        "documentId": document_id,
    })

    if "Item" not in response:
        return respond(404, {"error": "Document not found"})

    item = response["Item"]
    s3_key = item["s3Key"]

    # Check file exists in S3
    try:
        s3.head_object(Bucket=BUCKET, Key=s3_key)
    except Exception:
        return respond(404, {"error": "File not found in storage"})

    # Generate download URL (valid 1 hour)
    download_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": s3_key},
        ExpiresIn=3600,
    )

    return respond(200, {
        "fileName": item["fileName"],
        "docType": item["docType"],
        "downloadUrl": download_url,
        "expiresIn": "1 hour",
    })


def handle_list(params):
    """
    List all documents for an employee.
    Query: ?employeeId=E001
    Optional: ?employeeId=E001&docType=id_proof
    """
    employee_id = params.get("employeeId")
    doc_type = params.get("docType")

    if not employee_id:
        return respond(400, {"error": "employeeId is required"})

    # Query DynamoDB
    if doc_type:
        # Filter by document type
        response = table.query(
            KeyConditionExpression="employeeId = :eid",
            FilterExpression="docType = :dtype",
            ExpressionAttributeValues={
                ":eid": employee_id,
                ":dtype": doc_type,
            }
        )
    else:
        response = table.query(
            KeyConditionExpression="employeeId = :eid",
            ExpressionAttributeValues={":eid": employee_id}
        )

    documents = response.get("Items", [])

    return respond(200, {
        "employeeId": employee_id,
        "totalDocuments": len(documents),
        "documents": documents,
    })


def respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body, default=str),
    }

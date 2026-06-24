"""
Retrieval Lambda - the query side of the document ingestion & retrieval workflow.

Exposed through API Gateway (POST /search):
  1. Accepts a search query.
  2. Embeds the query with Amazon Titan Text Embeddings V2 (Bedrock).
  3. Scans the DynamoDB vector table and computes cosine similarity in pure
     Python (no numpy layer needed).
  4. Returns the top-K most relevant chunks with their source and score.
"""

import json
import math
import os

import boto3

dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")

TABLE_NAME = os.environ["TABLE_NAME"]
EMBED_MODEL = os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0")
DEFAULT_TOP_K = int(os.environ.get("TOP_K", "4"))

table = dynamodb.Table(TABLE_NAME)


def _embed(text):
    response = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": text}),
    )
    return json.loads(response["body"].read())["embedding"]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _scan_all():
    """Read every chunk from the vector table (handles pagination)."""
    items = []
    response = table.scan()
    items.extend(response["Items"])
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response["Items"])
    return items


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Request body must be valid JSON"})

    query = payload.get("query")
    if not query:
        return _response(400, {"error": "Missing 'query' in request body"})
    top_k = int(payload.get("topK", DEFAULT_TOP_K))

    query_vec = _embed(query)

    scored = []
    for item in _scan_all():
        embedding = json.loads(item["embedding"])
        score = _cosine(query_vec, embedding)
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, item in scored[:top_k]:
        results.append({
            "source": item["source"],
            "score": round(score, 4),
            "text": item["text"],
        })

    return _response(200, {
        "query": query,
        "matches": len(results),
        "results": results,
    })

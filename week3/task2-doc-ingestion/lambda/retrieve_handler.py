"""
Retrieval Lambda - the query side of the document ingestion & retrieval workflow.

Exposed through API Gateway (POST /search). Retrieval is delegated to a managed
Amazon Bedrock Knowledge Base (vector store = OpenSearch Serverless):
  1. Accepts a search query.
  2. Calls the Bedrock Knowledge Base Retrieve API (it embeds the query with
     Titan and runs vector search internally).
  3. Returns the top-K most relevant chunks with their source and score.
"""

import json
import os

import boto3

agent_runtime = boto3.client("bedrock-agent-runtime")

KB_ID = os.environ["KB_ID"]
DEFAULT_TOP_K = int(os.environ.get("TOP_K", "4"))


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _source_name(result):
    uri = result.get("location", {}).get("s3Location", {}).get("uri", "")
    return uri.rsplit("/", 1)[-1] if uri else "unknown"


def lambda_handler(event, context):
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Request body must be valid JSON"})

    query = payload.get("query")
    if not query:
        return _response(400, {"error": "Missing 'query' in request body"})
    top_k = int(payload.get("topK", DEFAULT_TOP_K))

    response = agent_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
    )

    results = []
    for item in response.get("retrievalResults", []):
        results.append({
            "source": _source_name(item),
            "score": round(item.get("score", 0.0), 4),
            "text": item["content"]["text"],
        })

    return _response(200, {
        "query": query,
        "matches": len(results),
        "results": results,
    })

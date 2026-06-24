"""
Ingestion Lambda - triggered by S3 object uploads.

For each uploaded document it:
  1. Reads the object from S3.
  2. Splits the text into overlapping chunks.
  3. Embeds each chunk with Amazon Titan Text Embeddings V2 (Bedrock).
  4. Writes each chunk + embedding to the DynamoDB vector table.

This is the "ingestion" half of a document ingestion & retrieval workflow.
"""

import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")

TABLE_NAME = os.environ["TABLE_NAME"]
EMBED_MODEL = os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "100"))

table = dynamodb.Table(TABLE_NAME)


def _chunk_text(text):
    """Split text into overlapping chunks on paragraph boundaries.

    Line endings are normalised first so that documents authored on Windows
    (CRLF) split on blank lines correctly. Any paragraph longer than the
    chunk size is hard-split so a single large block never becomes one chunk.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Break very long paragraphs into fixed-size pieces up front.
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    paragraphs = []
    for para in raw_paragraphs:
        if len(para) <= CHUNK_SIZE:
            paragraphs.append(para)
        else:
            for start in range(0, len(para), CHUNK_SIZE):
                paragraphs.append(para[start:start + CHUNK_SIZE])

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_SIZE:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # carry overlap from the tail of the previous chunk
            tail = current[-CHUNK_OVERLAP:] if current else ""
            current = f"{tail}\n\n{para}".strip() if tail else para
    if current:
        chunks.append(current)
    return chunks


def _embed(text):
    response = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": text}),
    )
    return json.loads(response["body"].read())["embedding"]


def lambda_handler(event, context):
    ingested = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        obj = s3.get_object(Bucket=bucket, Key=key)
        text = obj["Body"].read().decode("utf-8", errors="replace")

        chunks = _chunk_text(text)
        now = datetime.now(timezone.utc).isoformat()

        with table.batch_writer() as batch:
            for i, chunk in enumerate(chunks):
                embedding = _embed(chunk)
                digest = hashlib.md5(f"{key}#{i}".encode()).hexdigest()[:12]
                batch.put_item(Item={
                    "chunkId": f"{key}#{i}-{digest}",
                    "source": key,
                    "chunkIndex": i,
                    "text": chunk,
                    # store the vector as a JSON string to avoid Decimal issues
                    "embedding": json.dumps(embedding),
                    "createdAt": now,
                })
                ingested += 1

        print(f"Ingested {len(chunks)} chunks from s3://{bucket}/{key}")

    return {"ingestedChunks": ingested}

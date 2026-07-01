"""
Provision a Bedrock Knowledge Base for the NovaCart help-center documents,
backed by the existing Amazon OpenSearch Serverless collection.

What it does (idempotent):
  index      - create the vector index in the OpenSearch Serverless collection
  create-kb  - create the Bedrock Knowledge Base (vector store = OSS collection)
  datasource - attach the S3 bucket as a data source
  ingest     - start an ingestion job and wait for it to finish
  status     - show KB / data source / last ingestion status
  retrieve   - test semantic retrieval:  python setup_knowledge_base.py retrieve "query"
  all        - index + create-kb + datasource + ingest

Prerequisites (already created for this account):
  - OpenSearch Serverless collection 'bedrock-knowledge-base-a4msz1'
  - IAM role  AmazonBedrockExecutionRoleForKB-novacart
  - AOSS data-access policy 'novacart-kb-access'
"""

import json
import ssl
import sys
import time
import urllib.error
import urllib.request

import boto3
import botocore.session
import urllib3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

urllib3.disable_warnings()

REGION = "ap-south-1"
ACCOUNT = "353211646521"

COLLECTION_ARN = f"arn:aws:aoss:{REGION}:{ACCOUNT}:collection/gx3lj008w2ctdz2fdwn5"
AOSS_HOST = "gx3lj008w2ctdz2fdwn5.ap-south-1.aoss.amazonaws.com"
# Reuse the KB-compatible vector index already present in the shared collection
# (created by a prior Knowledge Base; empty, dim 1024, standard Bedrock fields).
INDEX_NAME = "bedrock-knowledge-base-default-index"

EMBED_MODEL_ARN = f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
KB_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/AmazonBedrockExecutionRoleForKB-novacart"
BUCKET_ARN = f"arn:aws:s3:::novacart-kb-documents-{ACCOUNT}"
DOC_PREFIX = "documents/"

KB_NAME = "novacart-knowledge-base"
DATA_SOURCE_NAME = "novacart-s3-documents"

VECTOR_FIELD = "bedrock-knowledge-base-default-vector"
TEXT_FIELD = "AMAZON_BEDROCK_TEXT_CHUNK"
META_FIELD = "AMAZON_BEDROCK_METADATA"

agent = boto3.client("bedrock-agent", region_name=REGION, verify=False)
agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION, verify=False)
_session = botocore.session.get_session()
_ctx = ssl._create_unverified_context()


# ──────────────────────────────────────────────────────────────────────────
# OpenSearch Serverless vector index (signed requests)
# ──────────────────────────────────────────────────────────────────────────
def _aoss(method, path, payload=None):
    url = f"https://{AOSS_HOST}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    creds = _session.get_credentials().get_frozen_credentials()
    req = AWSRequest(method=method, url=url, data=data,
                     headers={"Content-Type": "application/json"})
    SigV4Auth(creds, "aoss", REGION).add_auth(req)
    r = urllib.request.Request(url, data=data, headers=dict(req.headers), method=method)
    with urllib.request.urlopen(r, context=_ctx, timeout=30) as resp:
        return resp.status, resp.read().decode()


def _index_exists():
    try:
        _aoss("GET", f"/{INDEX_NAME}/_mapping")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def create_index():
    if _index_exists():
        print(f"  reusing existing index '{INDEX_NAME}'")
        return
    body = {
        "settings": {"index": {"knn": True, "knn.algo_param.ef_search": 512}},
        "mappings": {"properties": {
            VECTOR_FIELD: {
                "type": "knn_vector", "dimension": 1024,
                "method": {"name": "hnsw", "engine": "faiss", "space_type": "l2",
                           "parameters": {"ef_construction": 512, "m": 16}},
            },
            TEXT_FIELD: {"type": "text"},
            META_FIELD: {"type": "text", "index": False},
        }},
    }
    for attempt in range(12):
        try:
            status, text = _aoss("PUT", f"/{INDEX_NAME}", body)
            print(f"  index created ({status})")
            return
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code == 400 and "resource_already_exists" in msg.lower():
                print("  index already exists")
                return
            if e.code == 403 or "authorization" in msg.lower():
                print(f"  attempt {attempt + 1}: access policy still propagating, waiting 15s...")
                time.sleep(15)
                continue
            raise SystemExit(f"  index creation failed: {e.code} {msg}")
    raise SystemExit("  index creation timed out waiting for access policy")


# ──────────────────────────────────────────────────────────────────────────
# Knowledge Base + data source
# ──────────────────────────────────────────────────────────────────────────
def find_kb():
    for kb in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]:
        if kb["name"] == KB_NAME:
            return kb["knowledgeBaseId"]
    return None


def create_kb():
    existing = find_kb()
    if existing:
        print(f"  KB already exists: {existing}")
        return existing
    resp = agent.create_knowledge_base(
        name=KB_NAME,
        description="NovaCart help-center knowledge base (OpenSearch Serverless).",
        roleArn=KB_ROLE_ARN,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {"embeddingModelArn": EMBED_MODEL_ARN},
        },
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": COLLECTION_ARN,
                "vectorIndexName": INDEX_NAME,
                "fieldMapping": {
                    "vectorField": VECTOR_FIELD,
                    "textField": TEXT_FIELD,
                    "metadataField": META_FIELD,
                },
            },
        },
    )
    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    print(f"  KB created: {kb_id}")
    return kb_id


def find_data_source(kb_id):
    for ds in agent.list_data_sources(knowledgeBaseId=kb_id, maxResults=100)["dataSourceSummaries"]:
        if ds["name"] == DATA_SOURCE_NAME:
            return ds["dataSourceId"]
    return None


def create_data_source(kb_id):
    existing = find_data_source(kb_id)
    if existing:
        print(f"  data source already exists: {existing}")
        return existing
    resp = agent.create_data_source(
        knowledgeBaseId=kb_id,
        name=DATA_SOURCE_NAME,
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": BUCKET_ARN,
                "inclusionPrefixes": [DOC_PREFIX],
            },
        },
        vectorIngestionConfiguration={
            "chunkingConfiguration": {
                "chunkingStrategy": "FIXED_SIZE",
                "fixedSizeChunkingConfiguration": {"maxTokens": 300, "overlapPercentage": 20},
            }
        },
    )
    ds_id = resp["dataSource"]["dataSourceId"]
    print(f"  data source created: {ds_id}")
    return ds_id


def ingest(kb_id, ds_id, wait=True):
    job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    job_id = job["ingestionJob"]["ingestionJobId"]
    print(f"  ingestion job started: {job_id}")
    if not wait:
        return job_id
    for _ in range(60):
        time.sleep(10)
        status = agent.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
        )["ingestionJob"]
        state = status["status"]
        print(f"  ingestion status: {state}")
        if state in ("COMPLETE", "FAILED"):
            stats = status.get("statistics", {})
            print(f"  statistics: {json.dumps(stats)}")
            return job_id
    print("  (still running - check later with: python setup_knowledge_base.py status)")
    return job_id


# ──────────────────────────────────────────────────────────────────────────
# Status + retrieval test
# ──────────────────────────────────────────────────────────────────────────
def status():
    kb_id = find_kb()
    if not kb_id:
        print("  KB not found")
        return
    kb = agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]
    print(f"  KB {kb_id}: {kb['status']}")
    ds_id = find_data_source(kb_id)
    if ds_id:
        jobs = agent.list_ingestion_jobs(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, maxResults=1,
            sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
        )["ingestionJobSummaries"]
        if jobs:
            print(f"  data source {ds_id}: last ingestion {jobs[0]['status']} "
                  f"({json.dumps(jobs[0].get('statistics', {}))})")


def retrieve(query, top_k=3):
    kb_id = find_kb()
    if not kb_id:
        raise SystemExit("KB not found - run: python setup_knowledge_base.py all")
    resp = agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
    )
    print(f"\nQuery: {query}")
    for i, r in enumerate(resp["retrievalResults"], 1):
        src = r.get("location", {}).get("s3Location", {}).get("uri", "?")
        score = round(r.get("score", 0.0), 4)
        text = r["content"]["text"].replace("\n", " ")[:160]
        print(f"  [{i}] score {score}  {src}\n      {text}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "index":
        create_index()
    elif cmd == "create-kb":
        create_kb()
    elif cmd == "datasource":
        create_data_source(create_kb())
    elif cmd == "ingest":
        kb_id = create_kb()
        ingest(kb_id, create_data_source(kb_id))
    elif cmd == "status":
        status()
    elif cmd == "retrieve":
        retrieve(" ".join(sys.argv[2:]) or "How long do refunds take?")
    elif cmd == "all":
        create_index()
        kb_id = create_kb()
        ds_id = create_data_source(kb_id)
        print("  waiting 20s for KB to become active before ingestion...")
        time.sleep(20)
        ingest(kb_id, ds_id)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

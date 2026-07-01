"""
Ingestion trigger Lambda - invoked by S3 object uploads.

When a document lands in the S3 documents/ prefix, this Lambda starts a Bedrock
Knowledge Base ingestion job. The managed Knowledge Base then re-syncs the S3
data source: it extracts, chunks, embeds (Titan), and indexes the content into
the OpenSearch Serverless vector store. The heavy lifting is done by the managed
Knowledge Base, not by this function.
"""

import os

import boto3
from botocore.exceptions import ClientError

agent = boto3.client("bedrock-agent")

KB_ID = os.environ["KB_ID"]
DATA_SOURCE_ID = os.environ["DATA_SOURCE_ID"]


def lambda_handler(event, context):
    """Start a Knowledge Base ingestion job when documents are uploaded."""
    keys = [
        record["s3"]["object"]["key"]
        for record in event.get("Records", [])
        if "s3" in record
    ]

    try:
        job = agent.start_ingestion_job(
            knowledgeBaseId=KB_ID,
            dataSourceId=DATA_SOURCE_ID,
            description=f"Auto-sync after upload: {', '.join(keys)[:180]}",
        )
    except ClientError as exc:
        # Only one ingestion job can run at a time per data source; if one is
        # already running it will include the new files, so treat this as OK.
        if exc.response["Error"]["Code"] == "ConflictException":
            print("Ingestion already in progress; new files will be included.")
            return {"status": "ingestion_already_running", "triggeredBy": keys}
        raise

    job_id = job["ingestionJob"]["ingestionJobId"]
    print(f"Started KB ingestion job {job_id} for {keys}")
    return {"ingestionJobId": job_id, "triggeredBy": keys}

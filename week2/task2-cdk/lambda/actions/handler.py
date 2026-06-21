"""
Lambda handler for /api/actions-for-today endpoint.
Replaces the FastAPI router + OpenAI client with AWS-native services.
"""

import json
import os
import sys
import time

import boto3
import pandas as pd

# Add shared layer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from scoring import stable_sort_dataframe  # noqa: E402

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

BUCKET = os.environ["DATA_BUCKET"]
CSV_KEY = os.environ.get("CSV_KEY", "data/store_issue_feature_matrix_ui_relevant_subset.csv")
PROMPT_KEY = os.environ.get("PROMPT_KEY", "data/ai_sales_prompt_v7.txt")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")


def _read_s3_text(key: str) -> str:
    """Read a text file from S3."""
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return obj["Body"].read().decode("utf-8")


def _read_s3_csv(key: str) -> pd.DataFrame:
    """Read a CSV file from S3 into a DataFrame."""
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return pd.read_csv(obj["Body"])


def _invoke_bedrock(prompt: str) -> str:
    """Invoke Amazon Bedrock with the given prompt and return the response text."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]


def _extract_json(text: str) -> dict:
    """Parse model output as JSON, handling ```json fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    parsed = json.loads(text)

    if not isinstance(parsed, dict):
        raise ValueError("Model response was valid JSON but not an object.")

    if "result" in parsed and isinstance(parsed["result"], dict):
        parsed = parsed["result"]
    elif "result" in parsed and isinstance(parsed["result"], str):
        parsed = json.loads(parsed["result"])

    return parsed


DETERMINISTIC_INSTRUCTION = """

DETERMINISTIC PRIORITY RULES - MUST FOLLOW:
- The table_json rows are already pre-ranked using deterministic business scoring.
- Every row includes "_priority_score" and "_deterministic_rank".
- Do not independently reorder priorities.
- Action priority 1 must be based on the lowest "_deterministic_rank" issue that supports a valid action.
- Action priority 2 must use the next lowest "_deterministic_rank", and so on.
- If two issues appear similarly important, keep the lower "_deterministic_rank" first.
- Use the ranking fields only to decide order; do not mention "_priority_score" or "_deterministic_rank" in the final customer-facing JSON unless needed as evidence.
"""


def handler(event, context):
    """
    AWS Lambda handler for GET /api/actions-for-today.
    Called via API Gateway REST API (proxy integration).
    """
    start_time = time.time()
    print("[Info] Starting actions-for-today Lambda execution...")

    try:
        # 1. Read CSV from S3 and score
        df = _read_s3_csv(CSV_KEY)
        ranked_df = stable_sort_dataframe(df)

        table_json = json.dumps(
            ranked_df.to_dict(orient="records"),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

        # 2. Read prompt template from S3
        prompt_template = _read_s3_text(PROMPT_KEY)
        prompt = prompt_template.format(table_json=table_json) + DETERMINISTIC_INSTRUCTION

        # 3. Call Bedrock
        response_text = _invoke_bedrock(prompt)

        # 4. Parse response
        parsed_json = _extract_json(response_text)

        elapsed = time.time() - start_time
        print(f"[Info] Completed in {elapsed:.2f}s")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
            "body": json.dumps(parsed_json, ensure_ascii=False),
        }

    except json.JSONDecodeError as e:
        print(f"[Error] JSON parse error: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": f"Model returned invalid JSON: {str(e)}"}),
        }
    except Exception as e:
        print(f"[Error] Unexpected error: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)}),
        }

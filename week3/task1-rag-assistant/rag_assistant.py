"""
NovaCart Support Assistant - a RAG (Retrieval-Augmented Generation) assistant
built on Amazon Bedrock.

Retrieval is served by a managed Amazon Bedrock Knowledge Base (vector store =
OpenSearch Serverless), provisioned in Week 3 Task 2. This script:
  1. Retrieves the most relevant help-center chunks for the question via the
     Knowledge Base Retrieve API.
  2. Builds a grounded prompt and generates an answer with Anthropic Claude 3
     Haiku - citing the source documents.

Usage:
  python rag_assistant.py ask "How long does shipping take?"
  python rag_assistant.py chat          # interactive loop
"""

import json
import sys

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Bedrock is not reachable over a verified corporate TLS proxy in this account,
# so we disable SSL verification for the SDK client only.
import urllib3
urllib3.disable_warnings()

REGION = "ap-south-1"
GEN_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"
KB_NAME = "novacart-knowledge-base"
TOP_K = 4

_bedrock = boto3.client("bedrock-runtime", region_name=REGION, verify=False)
_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION, verify=False)
_kb_id = None


def _get_kb_id():
    """Resolve the Knowledge Base id by name (cached)."""
    global _kb_id
    if _kb_id is None:
        control = boto3.client("bedrock-agent", region_name=REGION, verify=False)
        for kb in control.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]:
            if kb["name"] == KB_NAME:
                _kb_id = kb["knowledgeBaseId"]
                break
        else:
            raise RuntimeError(
                f"Knowledge base '{KB_NAME}' not found. Create it via "
                "week3/task2-doc-ingestion/setup_knowledge_base.py"
            )
    return _kb_id


def _invoke_bedrock(model_id, payload):
    """Invoke a Bedrock model with actionable error messages."""
    try:
        return _bedrock.invoke_model(modelId=model_id, body=json.dumps(payload))
    except NoCredentialsError as exc:
        raise RuntimeError(
            "AWS credentials not found. Configure credentials before running this script. "
            "Example (Git Bash): export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... "
            "AWS_SESSION_TOKEN=... AWS_REGION=ap-south-1"
        ) from exc
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        if code in {"ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException"}:
            raise RuntimeError(
                "AWS credentials are invalid or expired. Refresh your temporary credentials "
                "and try again."
            ) from exc
        if code in {"AccessDeniedException", "UnauthorizedOperation"}:
            raise RuntimeError(
                f"Access denied for model '{model_id}'. Confirm Bedrock model access is enabled in {REGION} "
                "and your IAM policy allows bedrock:InvokeModel."
            ) from exc
        raise RuntimeError(f"Bedrock invoke failed ({code}): {exc}") from exc


# ──────────────────────────────────────────────────────────────────────────
# Bedrock helpers
# ──────────────────────────────────────────────────────────────────────────
def generate(prompt):
    """Generate an answer with Claude 3 Haiku."""
    response = _invoke_bedrock(
        GEN_MODEL,
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return json.loads(response["body"].read())["content"][0]["text"]


# ──────────────────────────────────────────────────────────────────────────
# Retrieval (Bedrock Knowledge Base) + generation
# ──────────────────────────────────────────────────────────────────────────
def _retrieve(question, top_k=TOP_K):
    """Retrieve the most relevant help-center chunks from the Knowledge Base."""
    try:
        response = _agent_runtime.retrieve(
            knowledgeBaseId=_get_kb_id(),
            retrievalQuery={"text": question},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
        )
    except NoCredentialsError as exc:
        raise RuntimeError(
            "AWS credentials not found. Configure credentials before running this script."
        ) from exc
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise RuntimeError(f"Knowledge Base retrieve failed ({code}): {exc}") from exc

    hits = []
    for item in response.get("retrievalResults", []):
        uri = item.get("location", {}).get("s3Location", {}).get("uri", "")
        source = uri.rsplit("/", 1)[-1] if uri else "help-center"
        hits.append({
            "source": source,
            "score": round(item.get("score", 0.0), 4),
            "text": item["content"]["text"],
        })
    return hits


def ask(question, show_sources=True):
    """Answer a question using context retrieved from the Knowledge Base."""
    hits = _retrieve(question)

    if not hits:
        return ("I don't have that information in the NovaCart help-center. "
                "Please contact support for help.")

    context_blocks = []
    for rank, hit in enumerate(hits, 1):
        context_blocks.append(f"[Source {rank}: {hit['source']}]\n{hit['text']}")
    context = "\n\n".join(context_blocks)

    prompt = (
        "You are NovaCart's customer support assistant. Answer the customer's "
        "question using ONLY the context below. If the answer is not in the "
        "context, say you don't have that information and suggest contacting "
        "support. Be concise and friendly. Cite sources as [filename].\n\n"
        f"Context:\n{context}\n\n"
        f"Customer question: {question}\n\n"
        "Answer:"
    )

    answer = generate(prompt)
    if show_sources:
        sources = ", ".join(sorted({hit["source"] for hit in hits}))
        answer += f"\n\nSources used: {sources}"
    return answer


def chat():
    """Interactive question loop."""
    print("NovaCart Support Assistant (type 'exit' to quit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        print("\nAssistant:", ask(question), "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    command = sys.argv[1]
    try:
        if command == "ingest":
            print("Ingestion is handled by the managed Knowledge Base. Upload "
                  "documents to the S3 data source (Week 3 Task 2); the pipeline "
                  "embeds and indexes them automatically.")
        elif command == "ask":
            if len(sys.argv) < 3:
                print('Usage: python rag_assistant.py ask "your question"')
                return
            print(ask(" ".join(sys.argv[2:])))
        elif command == "chat":
            chat()
        else:
            print(__doc__)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

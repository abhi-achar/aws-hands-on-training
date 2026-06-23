"""
NovaCart Support Assistant - a simple RAG (Retrieval-Augmented Generation)
assistant built on Amazon Bedrock.

Pipeline:
  1. Ingest: read help-center docs, split into chunks, embed each chunk with
     Amazon Titan Text Embeddings V2, and save a local vector store (JSON).
  2. Ask: embed the user question, retrieve the most similar chunks by cosine
     similarity, build a grounded prompt, and generate an answer with
     Anthropic Claude 3 Haiku - citing the source documents.

Usage:
  python rag_assistant.py ingest
  python rag_assistant.py ask "How long does shipping take?"
  python rag_assistant.py chat          # interactive loop
"""

import glob
import json
import os
import sys

import boto3
import numpy as np

# Bedrock is not reachable over a verified corporate TLS proxy in this account,
# so we disable SSL verification for the SDK client only.
import urllib3
urllib3.disable_warnings()

REGION = "ap-south-1"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
GEN_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"

HERE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(HERE, "knowledge_base")
STORE_PATH = os.path.join(HERE, "vector_store.json")
TOP_K = 4

_bedrock = boto3.client("bedrock-runtime", region_name=REGION, verify=False)


# ──────────────────────────────────────────────────────────────────────────
# Bedrock helpers
# ──────────────────────────────────────────────────────────────────────────
def embed(text):
    """Return the Titan embedding vector for a piece of text."""
    response = _bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": text}),
    )
    return json.loads(response["body"].read())["embedding"]


def generate(prompt):
    """Generate an answer with Claude 3 Haiku."""
    response = _bedrock.invoke_model(
        modelId=GEN_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    return json.loads(response["body"].read())["content"][0]["text"]


# ──────────────────────────────────────────────────────────────────────────
# Ingestion: chunk docs and build the vector store
# ──────────────────────────────────────────────────────────────────────────
def _chunk_markdown(text):
    """Split a markdown doc into chunks at '## ' section boundaries."""
    chunks = []
    current = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            chunks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]


def ingest():
    """Read all knowledge base docs, embed their chunks, save the vector store."""
    records = []
    doc_paths = sorted(glob.glob(os.path.join(KB_DIR, "*.md")))
    if not doc_paths:
        print(f"No documents found in {KB_DIR}")
        return

    for path in doc_paths:
        source = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        for i, chunk in enumerate(_chunk_markdown(text)):
            vector = embed(chunk)
            records.append({
                "id": f"{source}#{i}",
                "source": source,
                "text": chunk,
                "embedding": vector,
            })
            print(f"  embedded {source}#{i} ({len(chunk)} chars)")

    with open(STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(records, handle)
    print(f"\nIngested {len(records)} chunks from {len(doc_paths)} documents -> {STORE_PATH}")


# ──────────────────────────────────────────────────────────────────────────
# Retrieval + generation
# ──────────────────────────────────────────────────────────────────────────
def _load_store():
    if not os.path.exists(STORE_PATH):
        print("Vector store not found. Run: python rag_assistant.py ingest")
        sys.exit(1)
    with open(STORE_PATH, "r", encoding="utf-8") as handle:
        records = json.load(handle)
    matrix = np.array([r["embedding"] for r in records], dtype=np.float32)
    return records, matrix


def _cosine_top_k(query_vec, matrix, k):
    query = np.array(query_vec, dtype=np.float32)
    query_norm = query / (np.linalg.norm(query) + 1e-9)
    matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    scores = matrix_norm @ query_norm
    top_idx = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in top_idx]


def ask(question, records=None, matrix=None, show_sources=True):
    """Answer a question using retrieved context from the knowledge base."""
    if records is None:
        records, matrix = _load_store()

    query_vec = embed(question)
    hits = _cosine_top_k(query_vec, matrix, TOP_K)

    context_blocks = []
    for rank, (idx, score) in enumerate(hits, 1):
        rec = records[idx]
        context_blocks.append(f"[Source {rank}: {rec['source']}]\n{rec['text']}")
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
        sources = ", ".join(sorted({records[i]["source"] for i, _ in hits}))
        answer += f"\n\nSources used: {sources}"
    return answer


def chat():
    """Interactive question loop."""
    records, matrix = _load_store()
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
        print("\nAssistant:", ask(question, records, matrix), "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    command = sys.argv[1]
    if command == "ingest":
        ingest()
    elif command == "ask":
        if len(sys.argv) < 3:
            print('Usage: python rag_assistant.py ask "your question"')
            return
        print(ask(" ".join(sys.argv[2:])))
    elif command == "chat":
        chat()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

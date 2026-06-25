"""
Week 3 Task 4: Compare Foundation Models for Different Use Cases.

This benchmark runs 3 Bedrock models across 5 NovaCart-themed use cases and
measures quality, latency, and output length. Results are printed as a formatted
comparison table and saved to results.json.

Models:
  - Claude 3 Haiku  (fast, low cost)
  - Claude 3 Sonnet (balanced quality/cost)
  - Llama 3 8B      (open source, fast)

Use cases (all NovaCart-themed):
  1. Customer support Q&A (short factual answer)
  2. Summarization (condense a customer complaint)
  3. Structured extraction (extract JSON from an order email)
  4. Creative marketing copy (write a promotional message)
  5. Code generation (write a Python function)

Usage:
  python compare_models.py
"""

import json
import time

import boto3
import urllib3

urllib3.disable_warnings()

REGION = "ap-south-1"
br = boto3.client("bedrock-runtime", region_name=REGION, verify=False)

# ──────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────
MODELS = [
    {
        "label": "Claude 3 Haiku",
        "id": "anthropic.claude-3-haiku-20240307-v1:0",
        "provider": "anthropic",
        "cost_per_1k_input": 0.00025,
        "cost_per_1k_output": 0.00125,
    },
    {
        "label": "Claude 3 Sonnet",
        "id": "anthropic.claude-3-sonnet-20240229-v1:0",
        "provider": "anthropic",
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
    },
    {
        "label": "Llama 3 8B",
        "id": "meta.llama3-8b-instruct-v1:0",
        "provider": "meta",
        "cost_per_1k_input": 0.0003,
        "cost_per_1k_output": 0.0006,
    },
]

# ──────────────────────────────────────────────────────────────────────────
# Use Cases
# ──────────────────────────────────────────────────────────────────────────
USE_CASES = [
    {
        "name": "Customer Support Q&A",
        "prompt": (
            "You are NovaCart's support agent. Answer in 1-2 sentences.\n\n"
            "Customer: I ordered 3 days ago and it still says 'Placed'. When will it ship?\n\n"
            "Answer:"
        ),
        "max_tokens": 100,
        "eval_criteria": "accuracy, brevity, friendly tone",
    },
    {
        "name": "Summarization",
        "prompt": (
            "Summarize this customer complaint in 2 bullet points:\n\n"
            "I placed order ORD-5521 on June 15 for a laptop stand and wireless mouse. "
            "The order was supposed to arrive by June 18 but it's now June 22 and I only "
            "received the mouse. The laptop stand tracking shows 'In Transit' for 4 days "
            "with no updates. I called support twice and was told to wait. This is very "
            "frustrating as I need the stand for my home office setup. I want either "
            "immediate delivery or a full refund for the missing item.\n\n"
            "Summary:"
        ),
        "max_tokens": 150,
        "eval_criteria": "completeness, conciseness, key details captured",
    },
    {
        "name": "Structured Extraction",
        "prompt": (
            "Extract order information from this email as JSON with fields: "
            "order_id, customer_name, issue_type, items_mentioned, urgency (low/medium/high).\n\n"
            "Email: Hi, I'm Priya Sharma. My order ORD-8834 arrived today but the "
            "Bluetooth speaker is damaged - the casing is cracked and it won't turn on. "
            "I need a replacement urgently as it's a birthday gift for tomorrow. "
            "The headphones in the same order are fine. Please help ASAP.\n\n"
            "JSON:"
        ),
        "max_tokens": 200,
        "eval_criteria": "valid JSON, all fields extracted correctly, urgency classification",
    },
    {
        "name": "Marketing Copy",
        "prompt": (
            "Write a short, engaging push notification (max 20 words) for NovaCart's "
            "flash sale: 40% off all electronics, today only, free express shipping."
        ),
        "max_tokens": 80,
        "eval_criteria": "creativity, urgency, within word limit, brand-appropriate",
    },
    {
        "name": "Code Generation",
        "prompt": (
            "Write a Python function `calculate_refund(order_total, days_since_delivery, "
            "is_damaged)` that returns the refund amount based on these rules:\n"
            "- If damaged: full refund regardless of days.\n"
            "- If within 7 days: full refund.\n"
            "- If 8-14 days: 50% refund.\n"
            "- If over 14 days: no refund (return 0).\n"
            "Include a docstring and type hints."
        ),
        "max_tokens": 300,
        "eval_criteria": "correctness, type hints, docstring, handles all cases",
    },
]


# ──────────────────────────────────────────────────────────────────────────
# Invoke helpers
# ──────────────────────────────────────────────────────────────────────────
def invoke_anthropic(model_id, prompt, max_tokens):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    t0 = time.time()
    response = br.invoke_model(modelId=model_id, body=json.dumps(body))
    latency = time.time() - t0
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    input_tokens = result["usage"]["input_tokens"]
    output_tokens = result["usage"]["output_tokens"]
    return text, latency, input_tokens, output_tokens


def invoke_meta(model_id, prompt, max_tokens):
    body = {
        "prompt": (
            f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
            f"{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        ),
        "max_gen_len": max_tokens,
        "temperature": 0.3,
    }
    t0 = time.time()
    response = br.invoke_model(modelId=model_id, body=json.dumps(body))
    latency = time.time() - t0
    result = json.loads(response["body"].read())
    text = result["generation"]
    input_tokens = result.get("prompt_token_count", 0)
    output_tokens = result.get("generation_token_count", 0)
    return text, latency, input_tokens, output_tokens


def invoke_model(model, prompt, max_tokens):
    if model["provider"] == "anthropic":
        return invoke_anthropic(model["id"], prompt, max_tokens)
    else:
        return invoke_meta(model["id"], prompt, max_tokens)


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────
def main():
    all_results = []

    for uc in USE_CASES:
        print(f"\n{'='*60}")
        print(f"Use Case: {uc['name']}")
        print(f"Eval criteria: {uc['eval_criteria']}")
        print(f"{'='*60}")

        for model in MODELS:
            try:
                text, latency, in_tok, out_tok = invoke_model(
                    model, uc["prompt"], uc["max_tokens"]
                )
                cost = (
                    in_tok / 1000 * model["cost_per_1k_input"]
                    + out_tok / 1000 * model["cost_per_1k_output"]
                )
                result = {
                    "use_case": uc["name"],
                    "model": model["label"],
                    "latency_s": round(latency, 2),
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "estimated_cost_usd": round(cost, 6),
                    "output": text.strip(),
                }
                all_results.append(result)
                print(f"\n  {model['label']:20} | {latency:.2f}s | {out_tok} tokens | ${cost:.6f}")
                print(f"  Output: {text.strip()[:120]}...")
            except Exception as e:
                print(f"\n  {model['label']:20} | ERROR: {str(e)[:80]}")
                all_results.append({
                    "use_case": uc["name"],
                    "model": model["label"],
                    "error": str(e)[:200],
                })

    # Save results
    with open("results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n\nResults saved to results.json ({len(all_results)} entries)")

    # Print summary table
    print("\n" + "=" * 80)
    print("SUMMARY: Latency & Cost Comparison")
    print("=" * 80)
    print(f"{'Use Case':<25} {'Model':<20} {'Latency':<10} {'Tokens':<10} {'Cost':<12}")
    print("-" * 80)
    for r in all_results:
        if "error" not in r:
            print(
                f"{r['use_case']:<25} {r['model']:<20} {r['latency_s']:<10.2f} "
                f"{r['output_tokens']:<10} ${r['estimated_cost_usd']:<12.6f}"
            )


if __name__ == "__main__":
    main()

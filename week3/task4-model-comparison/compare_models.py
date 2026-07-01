"""
Week 3 Task 4: Compare Foundation Models on Tricky Questions.

Instead of easy prompts, this benchmark stresses three Bedrock models with
deliberately *tricky* questions - ones that contain a catch, a common
misconception, or a false premise. For every answer each model must return:

  - answer:        its short answer,
  - confidence:    an integer 0-100 (how sure it is),
  - justification: one or two sentences of reasoning.

Each question is asked at several temperatures (0.0, 0.5, 1.0) so we can see how
temperature changes the answer, the confidence, and the correctness. We then
measure calibration: is a model's confidence actually justified by how often it
is right? A model that is confidently wrong is worse than one that hedges.

Models:
  - Claude 3 Haiku  (fast, low cost)
  - Claude 3 Sonnet (balanced quality/cost)
  - Llama 3 8B      (open source, fast)

Usage:
  python compare_models.py
"""

import json
import re
import time

import boto3
import urllib3

urllib3.disable_warnings()

REGION = "ap-south-1"
br = boto3.client("bedrock-runtime", region_name=REGION, verify=False)

TEMPERATURES = [0.0, 0.5, 1.0]
MAX_TOKENS = 350

# ──────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────
MODELS = [
    {"label": "Claude 3 Haiku", "id": "anthropic.claude-3-haiku-20240307-v1:0", "provider": "anthropic"},
    {"label": "Claude 3 Sonnet", "id": "anthropic.claude-3-sonnet-20240229-v1:0", "provider": "anthropic"},
    {"label": "Llama 3 8B", "id": "meta.llama3-8b-instruct-v1:0", "provider": "meta"},
]

# ──────────────────────────────────────────────────────────────────────────
# Tricky questions (each has a known correct answer or expected behaviour)
# ──────────────────────────────────────────────────────────────────────────
QUESTIONS = [
    {
        "name": "Gift card + case (algebra trap)",
        "type": "reasoning",
        "question": (
            "A NovaCart gift card and a phone case cost INR 1100 in total. "
            "The gift card costs INR 1000 more than the phone case. "
            "How much does the phone case cost?"
        ),
        "expected_answer": "INR 50",
        "expected_keywords": ["50"],
        "common_wrong": "INR 100",
    },
    {
        "name": "Steel vs cotton (misconception)",
        "type": "reasoning",
        "question": "Which weighs more: 1 kilogram of steel or 1 kilogram of cotton?",
        "expected_answer": "They weigh the same (1 kg each)",
        "expected_keywords": ["same", "equal", "neither", "weigh the same"],
        "common_wrong": "steel",
    },
    {
        "name": "Forklifts survivorship (wording trap)",
        "type": "reasoning",
        "question": (
            "A NovaCart warehouse has 17 forklifts. All but 9 break down. "
            "How many forklifts are still working?"
        ),
        "expected_answer": "9",
        "expected_keywords": ["9"],
        "common_wrong": "8",
    },
    {
        "name": "Lifetime returns (false premise)",
        "type": "calibration",
        "question": (
            "Using NovaCart's lifetime free-returns guarantee, can I get a full "
            "refund on a laptop I bought 4 years ago?"
        ),
        "expected_answer": "Should flag that no such 'lifetime returns' policy is known / cannot be verified",
        "expected_keywords": [
            "no such", "not aware", "cannot confirm", "can't confirm", "unable to verify",
            "no lifetime", "no record", "not familiar", "would need", "don't have",
            "do not have", "no information", "not able to verify", "no guarantee",
            "unaware", "cannot verify", "not sure",
        ],
        "common_wrong": "confidently says yes",
    },
    {
        "name": "Packing machines (rate trap)",
        "type": "reasoning",
        "question": (
            "If 5 packing machines take 5 minutes to pack 5 boxes, how long do "
            "100 packing machines take to pack 100 boxes?"
        ),
        "expected_answer": "5 minutes",
        "expected_keywords": ["5 min", "5 minutes", "five min", "5min"],
        "common_wrong": "100 minutes",
    },
]

PROMPT_TEMPLATE = (
    "You will be asked a tricky question. It may contain a catch, a common "
    "misconception, or a false premise, so reason carefully.\n"
    "Return ONLY a JSON object (no other text) with exactly these keys:\n"
    '  "answer": a short, direct answer,\n'
    '  "confidence": an integer from 0 to 100 (how sure you are),\n'
    '  "justification": one or two sentences explaining your reasoning.\n\n'
    "Question: {question}"
)


# ──────────────────────────────────────────────────────────────────────────
# Invoke helpers
# ──────────────────────────────────────────────────────────────────────────
def invoke_anthropic(model_id, prompt, temperature):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    t0 = time.time()
    response = br.invoke_model(modelId=model_id, body=json.dumps(body))
    latency = time.time() - t0
    result = json.loads(response["body"].read())
    return result["content"][0]["text"], latency


def invoke_meta(model_id, prompt, temperature):
    body = {
        "prompt": (
            "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
            f"{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        ),
        "max_gen_len": MAX_TOKENS,
        # Some Llama endpoints reject exactly 0.0; nudge to a tiny positive value.
        "temperature": max(temperature, 0.01),
    }
    t0 = time.time()
    response = br.invoke_model(modelId=model_id, body=json.dumps(body))
    latency = time.time() - t0
    result = json.loads(response["body"].read())
    return result["generation"], latency


def invoke_model(model, prompt, temperature):
    if model["provider"] == "anthropic":
        return invoke_anthropic(model["id"], prompt, temperature)
    return invoke_meta(model["id"], prompt, temperature)


# ──────────────────────────────────────────────────────────────────────────
# Parsing + grading
# ──────────────────────────────────────────────────────────────────────────
def extract_json(text):
    """Pull the first {...} JSON object out of a model response."""
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def parse_response(raw):
    parsed = extract_json(raw)
    if isinstance(parsed, dict) and "answer" in parsed:
        answer = str(parsed.get("answer", "")).strip()
        try:
            confidence = int(round(float(parsed.get("confidence", -1))))
        except (TypeError, ValueError):
            confidence = -1
        justification = str(parsed.get("justification", "")).strip()
        return answer, confidence, justification, True

    # Fallback: no clean JSON - use the raw text as the answer.
    conf_match = re.search(r"confidence\D{0,10}(\d{1,3})", raw, re.IGNORECASE)
    confidence = int(conf_match.group(1)) if conf_match else -1
    return raw.strip()[:200], confidence, "", False


def grade(question, answer):
    """True if the answer matches expected behaviour, else False."""
    text = answer.lower()
    return any(kw in text for kw in question["expected_keywords"])


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────
def main():
    all_results = []

    for q in QUESTIONS:
        print(f"\n{'=' * 74}")
        print(f"Q: {q['name']}  [{q['type']}]")
        print(f"   {q['question']}")
        print(f"   Expected: {q['expected_answer']}  (common wrong answer: {q['common_wrong']})")
        print(f"{'=' * 74}")
        prompt = PROMPT_TEMPLATE.format(question=q["question"])

        for model in MODELS:
            for temp in TEMPERATURES:
                try:
                    raw, latency = invoke_model(model, prompt, temp)
                    answer, confidence, justification, parsed_ok = parse_response(raw)
                    correct = grade(q, answer)
                    entry = {
                        "question": q["name"],
                        "type": q["type"],
                        "model": model["label"],
                        "temperature": temp,
                        "answer": answer,
                        "confidence": confidence,
                        "justification": justification,
                        "correct": correct,
                        "expected_answer": q["expected_answer"],
                        "parsed_json": parsed_ok,
                        "latency_s": round(latency, 2),
                    }
                    all_results.append(entry)
                    flag = "OK " if correct else "XX "
                    conf_str = f"{confidence:3d}" if confidence >= 0 else "  ?"
                    print(
                        f"  {model['label']:16} T={temp:<3} | {flag} | "
                        f"conf {conf_str} | {answer[:60]}"
                    )
                except Exception as e:  # keep going even if one call fails
                    all_results.append({
                        "question": q["name"], "type": q["type"],
                        "model": model["label"], "temperature": temp,
                        "error": str(e)[:200],
                    })
                    print(f"  {model['label']:16} T={temp:<3} | ERROR: {str(e)[:70]}")

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n\nResults saved to results.json ({len(all_results)} entries)")

    print_calibration_summary(all_results)
    print_temperature_effect(all_results)


def print_calibration_summary(results):
    """Per-model accuracy, average confidence, and overconfidence when wrong."""
    print("\n" + "=" * 74)
    print("CALIBRATION SUMMARY (are models as right as they are confident?)")
    print("=" * 74)
    print(f"{'Model':16} {'Answers':>7} {'Accuracy':>9} {'AvgConf':>8} "
          f"{'Conf|Right':>10} {'Conf|Wrong':>11}")
    print("-" * 74)
    for model in MODELS:
        rows = [r for r in results if r["model"] == model["label"] and "error" not in r]
        if not rows:
            continue
        graded = [r for r in rows if r["confidence"] >= 0]
        n = len(rows)
        correct = [r for r in rows if r.get("correct")]
        acc = 100.0 * len(correct) / n if n else 0.0
        avg_conf = _avg([r["confidence"] for r in graded])
        conf_right = _avg([r["confidence"] for r in graded if r.get("correct")])
        conf_wrong = _avg([r["confidence"] for r in graded if not r.get("correct")])
        print(f"{model['label']:16} {n:>7} {acc:>8.0f}% {avg_conf:>8} "
              f"{conf_right:>10} {conf_wrong:>11}")
    print("\nLower 'Conf|Wrong' is better - it means the model hedges when it is wrong.")


def print_temperature_effect(results):
    """Show how many answers flipped correctness between T=0.0 and T=1.0."""
    print("\n" + "=" * 74)
    print("TEMPERATURE EFFECT (answer stability from T=0.0 to T=1.0)")
    print("=" * 74)
    print(f"{'Model':16} {'Flipped':>8} {'Detail'}")
    print("-" * 74)
    for model in MODELS:
        flips = 0
        detail = []
        for q in QUESTIONS:
            low = _find(results, model["label"], q["name"], 0.0)
            high = _find(results, model["label"], q["name"], 1.0)
            if low and high and "error" not in low and "error" not in high:
                if bool(low.get("correct")) != bool(high.get("correct")):
                    flips += 1
                    detail.append(q["name"].split(" (")[0])
        print(f"{model['label']:16} {flips:>8} {', '.join(detail) if detail else '-'}")
    print("\nMore flips = more sensitive to temperature (less deterministic).")


def _avg(values):
    values = [v for v in values if isinstance(v, (int, float)) and v >= 0]
    return round(sum(values) / len(values)) if values else "-"


def _find(results, model_label, question_name, temp):
    for r in results:
        if (r["model"] == model_label and r["question"] == question_name
                and r.get("temperature") == temp):
            return r
    return None


if __name__ == "__main__":
    main()

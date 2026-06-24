"""
NovaCart Support Agent - basic tool-calling with the Strands Agents SDK.

The agent runs on Amazon Bedrock (Claude 3 Haiku) and is given three tools.
The model decides which tool(s) to call for each customer question:

  1. search_help_center  -> calls the deployed document-retrieval API (Week 3
     Task 2) for grounded policy answers.
  2. get_order_status    -> looks up an order in a simulated order system.
  3. check_return_eligibility -> applies NovaCart's return-policy business rules.

This demonstrates how an LLM agent orchestrates external tools/services instead
of answering from memory alone.

Usage:
  python support_agent.py "Where is order ORD-1001 and can I return it?"
  python support_agent.py            # interactive chat
"""

import sys

import boto3
import requests
import urllib3

urllib3.disable_warnings()

# Corporate TLS proxy: force every boto3 client (including the one Strands
# creates for Bedrock) to skip SSL verification.
_orig_client = boto3.session.Session.client


def _client_no_verify(self, *args, **kwargs):
    kwargs.setdefault("verify", False)
    return _orig_client(self, *args, **kwargs)


boto3.session.Session.client = _client_no_verify

from strands import Agent, tool  # noqa: E402
from strands.models import BedrockModel  # noqa: E402

REGION = "ap-south-1"
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
SEARCH_API = "https://tdf4du7z9g.execute-api.ap-south-1.amazonaws.com/prod/search"

# A small simulated order system. In production this tool would call an
# internal order-management API or database.
ORDERS = {
    "ORD-1001": {
        "status": "Out for Delivery",
        "items": "Wireless Headphones",
        "category": "electronics",
        "total": 2499,
        "delivered": False,
        "days_since_delivery": None,
    },
    "ORD-1002": {
        "status": "Delivered",
        "items": "Cotton T-Shirt",
        "category": "fashion",
        "total": 799,
        "delivered": True,
        "days_since_delivery": 3,
    },
    "ORD-1003": {
        "status": "Delivered",
        "items": "Bluetooth Earphones",
        "category": "earphones",
        "total": 1299,
        "delivered": True,
        "days_since_delivery": 10,
    },
}


# ──────────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────────
@tool
def search_help_center(query: str) -> str:
    """Search NovaCart's help-center for policy and how-to information.

    Use this for questions about shipping, refunds, payments, returns policy,
    accounts, or anything answered by NovaCart's documentation.

    Args:
        query: The customer's question or search phrase.
    """
    try:
        response = requests.post(
            SEARCH_API, json={"query": query, "topK": 3}, verify=False, timeout=20
        )
        results = response.json().get("results", [])
    except Exception as exc:  # network/parse safety at the tool boundary
        return f"Help-center search is unavailable right now ({exc})."

    if not results:
        return "No relevant help-center articles were found."
    snippets = []
    for r in results:
        snippets.append(f"From {r['source']} (score {r['score']}): {r['text']}")
    return "\n\n".join(snippets)


@tool
def get_order_status(order_id: str) -> str:
    """Look up the current status and details of a NovaCart order.

    Args:
        order_id: The order identifier, for example ORD-1001.
    """
    order = ORDERS.get(order_id.upper().strip())
    if not order:
        return f"No order found with id {order_id}."
    return (
        f"Order {order_id.upper()}: {order['items']} (category: {order['category']}). "
        f"Status: {order['status']}. Total: INR {order['total']}. "
        f"Delivered: {order['delivered']}"
        + (
            f", {order['days_since_delivery']} days ago."
            if order["delivered"]
            else "."
        )
    )


@tool
def check_return_eligibility(category: str, days_since_delivery: int) -> str:
    """Check whether an item can be returned under NovaCart's return policy.

    Policy: returns are allowed within 7 days of delivery, except earphones,
    innerwear, and personal grooming items, which are non-returnable.

    Args:
        category: The product category, for example electronics, fashion, earphones.
        days_since_delivery: Number of days since the item was delivered.
    """
    non_returnable = {"earphones", "innerwear", "grooming"}
    if category.lower() in non_returnable:
        return f"Items in category '{category}' are non-returnable for hygiene/safety reasons."
    if days_since_delivery > 7:
        return (
            f"This item was delivered {days_since_delivery} days ago, which is "
            "outside the 7-day return window. It is not eligible for return."
        )
    return (
        f"This '{category}' item was delivered {days_since_delivery} days ago and "
        "is within the 7-day window, so it is eligible for return."
    )


SYSTEM_PROMPT = (
    "You are NovaCart's AI customer-support agent. Use the available tools to "
    "answer questions about orders, returns, and policies. Look up real order "
    "details and policy information with the tools instead of guessing. Be "
    "concise, friendly, and accurate. If something cannot be determined from "
    "the tools, say so and suggest contacting support."
)


def build_agent():
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    return Agent(
        model=model,
        tools=[search_help_center, get_order_status, check_return_eligibility],
        system_prompt=SYSTEM_PROMPT,
    )


def main():
    agent = build_agent()
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(agent(question))
        return
    print("NovaCart Support Agent (type 'exit' to quit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"exit", "quit"}:
            break
        if question:
            print("\nAgent:", agent(question), "\n")


if __name__ == "__main__":
    main()

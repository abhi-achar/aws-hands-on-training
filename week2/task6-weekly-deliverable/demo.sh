#!/usr/bin/env bash
#
# Week 2 Weekly Deliverable - End-to-End Demo
#
# Drives the full integrated system:
#   API Gateway -> Lambda -> Step Functions orchestration -> DynamoDB + SNS
#
# Usage: bash demo.sh

API="https://r6k62pk8oj.execute-api.ap-south-1.amazonaws.com/prod"

post_order() {
  label="$1"
  body="$2"
  echo "=============================================="
  echo "Scenario: ${label}"
  echo "----------------------------------------------"

  resp=$(curl -sk -X POST "${API}/orders" -H "Content-Type: application/json" -d "${body}")
  echo "POST /orders -> ${resp}"

  eid=$(echo "${resp}" | python -c "import json,sys; print(json.load(sys.stdin)['executionId'])")
  echo "Polling status for: ${eid}"

  i=1
  while [ "${i}" -le 6 ]; do
    sleep 5
    status_resp=$(curl -sk "${API}/orders/${eid}")
    status=$(echo "${status_resp}" | python -c "import json,sys; print(json.load(sys.stdin)['status'])")
    echo "  poll ${i}: ${status}"
    if [ "${status}" != "RUNNING" ]; then
      echo "Final result:"
      echo "${status_resp}" | python -m json.tool
      break
    fi
    i=$((i + 1))
  done
  echo ""
}

# Scenario 1: Happy path (order is confirmed)
post_order "Happy path (PROD-002, in stock)" \
  '{"order":{"customerId":"DEMO-OK","items":[{"productId":"PROD-002","quantity":2,"price":1200}],"shippingAddress":"Bangalore"}}'

# Scenario 2: Out of stock (orchestration inventory branch fails)
post_order "Out of stock (PROD-003, 0 stock)" \
  '{"order":{"customerId":"DEMO-OOS","items":[{"productId":"PROD-003","quantity":1,"price":499}],"shippingAddress":"Bangalore"}}'

echo "Demo complete."

# Task 2: DynamoDB CRUD Operations

## What was built
- DynamoDB table with on-demand capacity
- Lambda function performing Create, Read, Update, Delete
- API Gateway integration for RESTful access

## Table Schema
- Table: `actions-table`
- Partition Key: `actionId` (String)
- Billing: PAY_PER_REQUEST

## Key Commands
```bash
aws dynamodb create-table --table-name actions-table \
  --attribute-definitions AttributeName=actionId,AttributeType=S \
  --key-schema AttributeName=actionId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

aws dynamodb put-item --table-name actions-table \
  --item '{"actionId":{"S":"A001"},"title":{"S":"Follow up with client"}}'

aws dynamodb scan --table-name actions-table
```

# Task 1: Multi-step Workflows with Step Functions

## What was built
- 4 Lambda functions forming an order processing pipeline
- Step Functions state machine with parallel execution, retries, error handling
- SNS notifications for order confirmation/failure

## Architecture
```
ValidateOrder -> Valid? -No-> Rejected
                       -Yes-> CheckInventory -> InStock? -No-> Notify -> Fail
                                                        -Yes-> Payment -> Wait -> [SaveDB || SendEmail] -> Complete
                                                                 (error)-> Notify -> Fail
```

## Lambda Functions
| Function | Purpose |
|----------|---------|
| validate-order | Validates fields, calculates total |
| check-inventory | Checks simulated stock levels |
| process-payment | Simulates payment processing |
| update-order | Saves to DynamoDB |

## Test Commands
```bash
# Happy path
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:ap-south-1:353211646521:stateMachine:OrderProcessingWorkflow \
  --input '{"order":{"customerId":"C001","items":[{"productId":"PROD-001","quantity":1,"price":2499}],"shippingAddress":"Bangalore"}}'

# Out of stock (PROD-003)
# Payment failure (customerId ending in "FAIL")
# Invalid order (missing fields)
```

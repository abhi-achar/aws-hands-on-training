# Task 2: Infrastructure as Code with AWS CDK

## What was built
- Same pipeline as Task 1, defined in Python CDK (~280 lines)
- Single command deploys: DynamoDB + SNS + 4 Lambdas + Step Functions + IAM
- All resources suffixed with `-cdk` to avoid conflicts

## Key Files (in repo root)
- `cdk/order_processing_stack.py` - Stack definition
- `lambda/step_functions/` - Lambda source
- `app.py` - CDK entry point

## CDK Highlights
- `Code.from_inline()` - No bootstrap needed
- `.grant_read_write_data()` - Auto IAM policies
- `sfn.Parallel` - Concurrent execution branches

## Deploy Commands
```bash
cdk synth
aws cloudformation create-stack --stack-name OrderProcessingStack \
  --template-body file://cdk.out/OrderProcessingStack.template.json \
  --capabilities CAPABILITY_NAMED_IAM
```

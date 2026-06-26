# Task 2: Deploy Infrastructure Using AWS CDK

## Goal
Recreate the Step Functions order-processing infrastructure as code using AWS CDK in Python, then deploy it through CloudFormation.

## Architecture
```mermaid
flowchart TD
    Code["🐍 CDK Python code<br/>order_processing_stack.py"]:::iac
    Synth["⚙️ cdk synth"]:::iac
    Template["📄 CloudFormation template<br/>OrderProcessingStack.template.json"]:::iac
    Deploy["☁️ CloudFormation deploy"]:::iac
    subgraph Stack["📦 OrderProcessingStack · ap-south-1"]
        R1["🗄️ DynamoDB<br/><b>order-processing-cdk</b>"]:::db
        R2["📢 SNS<br/><b>order-notifications-cdk</b>"]:::messaging
        R3["λ 4x Lambda<br/>validate · inventory<br/>payment · update"]:::lambda
        R4["🔀 Step Functions<br/><b>OrderProcessingWorkflow-CDK</b>"]:::sfn
        R5["🔐 IAM Roles<br/>auto-generated"]:::iam
    end
    Code ==> Synth ==> Template ==> Deploy
    Deploy --> R1
    Deploy --> R2
    Deploy --> R3
    Deploy --> R4
    Deploy --> R5

    classDef iac fill:#8C4FFF,stroke:#6B2FD6,stroke-width:2px,color:#ffffff
    classDef db fill:#4053D6,stroke:#2E3FA8,stroke-width:2px,color:#ffffff
    classDef messaging fill:#E7157B,stroke:#B30E5F,stroke-width:2px,color:#ffffff
    classDef lambda fill:#FF9900,stroke:#E88B00,stroke-width:2px,color:#ffffff
    classDef sfn fill:#CD2264,stroke:#9E1A4D,stroke-width:2px,color:#ffffff
    classDef iam fill:#DD344C,stroke:#A82538,stroke-width:2px,color:#ffffff
```

## Resources Created
| Service | Resource |
|---|---|
| DynamoDB | order-processing-cdk |
| SNS | order-notifications-cdk |
| Lambda | validate-order-cdk |
| Lambda | check-inventory-cdk |
| Lambda | process-payment-cdk |
| Lambda | update-order-cdk |
| Step Functions | OrderProcessingWorkflow-CDK |
| CloudFormation | OrderProcessingStack |

## Key Files
| File/Folder | Purpose |
|---|---|
| app.py | CDK app entry point |
| cdk/order_processing_stack.py | Main CDK stack definition |
| lambda/step_functions/ | Lambda source code used by CDK |
| requirements.txt | Python CDK dependencies |
| cdk.json | CDK CLI configuration |

## Important CDK Concepts Used
- `dynamodb.Table` creates the order table.
- `sns.Topic` creates the notification topic.
- `lambda.Function` creates each Lambda.
- `Code.from_inline()` embeds Lambda code directly in the template to avoid CDK bootstrap constraints.
- `order_table.grant_read_write_data(update_order_fn)` creates least-scoped DynamoDB IAM permissions.
- `tasks.LambdaInvoke` creates Step Functions Lambda tasks.
- `sfn.Choice`, `sfn.Fail`, `sfn.Wait`, and `sfn.Parallel` build the workflow.
- `CfnOutput` exposes stack outputs.

## Step-by-Step Setup
1. Install Python dependencies.
2. Verify AWS credentials for account `353211646521` and region `ap-south-1`.
3. Run `cdk synth` to generate a CloudFormation template.
4. Deploy the template with CloudFormation.
5. Confirm the stack reaches `CREATE_COMPLETE` or `UPDATE_COMPLETE`.
6. Start a Step Functions execution to validate the deployment.

## How to Run Locally
```bash
cd week2/task2-cdk
pip install -r requirements.txt
cdk synth
```

## Deploy Command
```bash
aws cloudformation create-stack   --stack-name OrderProcessingStack   --template-body file://cdk.out/OrderProcessingStack.template.json   --capabilities CAPABILITY_NAMED_IAM   --region ap-south-1   --no-verify-ssl
```

For updates:
```bash
aws cloudformation update-stack   --stack-name OrderProcessingStack   --template-body file://cdk.out/OrderProcessingStack.template.json   --capabilities CAPABILITY_NAMED_IAM   --region ap-south-1   --no-verify-ssl
```

## Test Command
```bash
aws stepfunctions start-execution   --state-machine-arn arn:aws:states:ap-south-1:353211646521:stateMachine:OrderProcessingWorkflow-CDK   --input '{"order":{"customerId":"C001","items":[{"productId":"PROD-001","quantity":1,"price":2499}],"shippingAddress":"CDK Deployed, Bangalore"}}'   --region ap-south-1   --no-verify-ssl
```

## What to Verify
- CloudFormation stack `OrderProcessingStack` exists.
- Stack outputs include `StateMachineArn`, `TableName`, and `TopicArn`.
- Step Functions execution succeeds.
- DynamoDB table `order-processing-cdk` contains the confirmed order.

## End-to-End Flow, Solution & Service Choices
1. CDK Python code defines workflow infrastructure as constructs.
2.  converts constructs into a CloudFormation template.
3. CloudFormation creates/updates resources in a transactional deployment.
4. Deployed Step Functions workflow is executed and validated.

### Why this solution
- Infrastructure as Code ensures repeatable, versioned, and reviewable cloud changes.
- CDK improves developer productivity with real programming abstractions while still producing standard CloudFormation.

### Why these AWS services
- AWS CDK: higher-level IaC abstraction with reusable constructs.
- CloudFormation: managed deployment engine with drift protection and rollback behavior.
- Step Functions/Lambda/DynamoDB/SNS: core runtime services required by the order workflow.

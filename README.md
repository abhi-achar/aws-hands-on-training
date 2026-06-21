# SCJ Sales Coach - AWS Infrastructure

## Architecture

```
Client (React FE)
    │
    ▼
API Gateway (REST)
    ├── GET /                      → Health Check Lambda
    └── GET /api/actions-for-today → Actions Lambda
                                        ├── Reads CSV from S3
                                        ├── Scores with deterministic logic
                                        └── Calls Amazon Bedrock (Claude)
```

## Prerequisites

1. **AWS CLI** configured with your credentials:
   ```bash
   aws configure
   ```

2. **Node.js** (required by CDK):
   ```bash
   node --version  # v18+
   ```

3. **AWS CDK CLI**:
   ```bash
   npm install -g aws-cdk
   cdk --version
   ```

4. **Python 3.12+** with a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/Mac:
   source .venv/bin/activate
   ```

5. **Docker** (required for Lambda bundling with CDK)

## Setup & Deploy

```bash
# 1. Navigate to infra directory
cd SCJ-sales-coach-infra

# 2. Install CDK dependencies
pip install -r requirements.txt

# 3. Bootstrap CDK (first time only, per account/region)
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# 4. Synthesize the CloudFormation template (validate)
cdk synth

# 5. Deploy the stack
cdk deploy SalesCoachApiStack
```

After deployment, CDK will output:
- **ApiUrl** – Your API Gateway endpoint (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com/prod/`)
- **BucketName** – S3 bucket where CSV/prompt data is stored

## Test the API

```bash
# Health check
curl https://<API_URL>/

# Get actions (calls Bedrock - may take 15-30s)
curl https://<API_URL>/api/actions-for-today
```

## Project Structure

```
SCJ-sales-coach-infra/
├── app.py                  # CDK app entry point
├── cdk.json                # CDK configuration
├── requirements.txt        # CDK Python dependencies
├── cdk/
│   ├── __init__.py
│   └── api_stack.py        # Main stack: API GW + Lambda + S3
└── lambda/
    ├── requirements.txt    # Lambda runtime dependencies
    ├── actions/
    │   ├── handler.py      # GET /api/actions-for-today
    │   └── health.py       # GET /
    └── shared/
        ├── helpers.py      # Utility functions
        └── scoring.py      # Deterministic priority scoring
```

## How It Maps to Your Existing Code

| Original (FastAPI on Azure) | AWS Serverless |
|-----------------------------|----------------|
| `app/routers/actions.py` | `lambda/actions/handler.py` |
| `app/services/openai_client.py` | Bedrock call in `handler.py` |
| `app/services/scoring.py` | `lambda/shared/scoring.py` |
| `app/utils/helpers.py` | `lambda/shared/helpers.py` |
| `data/*.csv`, `data/*.txt` | S3 bucket (`data/` prefix) |
| Azure App Service | API Gateway + Lambda |

## Cleanup

```bash
cdk destroy SalesCoachApiStack
```

## Next Steps (Week 1 continued)

- [ ] Add DynamoDB table to cache generated results
- [ ] Add S3 event trigger (new CSV upload → re-generate actions)
- [ ] Add EventBridge/SQS for async processing
- [ ] Add CloudWatch alarms for errors

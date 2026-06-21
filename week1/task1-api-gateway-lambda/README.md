# Task 1: REST API with API Gateway + Lambda

## What was built
- REST API with multiple endpoints (GET, POST)
- Lambda function (Python 3.12) as backend
- API Gateway with resource paths and method integrations

## Architecture
Client -> API Gateway -> Lambda -> Response

## Key Commands
```bash
aws lambda create-function --function-name my-api-handler \
  --runtime python3.12 --handler lambda_function.lambda_handler \
  --role arn:aws:iam::353211646521:role/lambda-execution-role \
  --zip-file fileb://function.zip

aws apigateway create-rest-api --name "training-api"
aws apigateway create-deployment --rest-api-id <id> --stage-name prod
```

## API URL
https://kboq3nibic.execute-api.ap-south-1.amazonaws.com/prod/

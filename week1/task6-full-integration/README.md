# Task 6: Full-stack Integration

## What was built
- Complete serverless application
- Frontend (S3 + CloudFront) calling Backend (API Gateway + Lambda + DynamoDB)
- Cognito authentication protecting API endpoints

## Architecture
```
Browser -> CloudFront -> S3 (Frontend)
         |
         v (API calls with JWT)
   API Gateway (Cognito Authorizer) -> Lambda -> DynamoDB
```

## API URL
https://2510k20042.execute-api.ap-south-1.amazonaws.com/prod/

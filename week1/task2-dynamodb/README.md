# Task 2: Event-Driven Flow with S3, SQS, Lambda, and SNS

## Goal
Build an event-driven pipeline where uploading a CSV file to S3 triggers report generation through SQS and Lambda, then sends a notification through SNS.

## Architecture
```text
CSV upload
   |
   v
S3 bucket: scj-sales-uploads
   |
   v
SQS queue: sales-report-queue
   |
   v
Lambda: sales-report-generator
   |
   v
SNS topic: sales-report-notifications
   |
   v
Email notification

Failure path: sales-report-queue -> sales-report-dlq after 3 failed receives
```

## Resources Created
| Service | Resource | Purpose |
|---|---|---|
| S3 | scj-sales-uploads | Receives CSV uploads under uploads/ |
| SQS | sales-report-queue | Main event queue |
| SQS | sales-report-dlq | Dead letter queue |
| Lambda | sales-report-generator | Reads CSV and generates summary |
| SNS | sales-report-notifications | Sends email notification |

## Important Values
```text
Queue URL: https://sqs.ap-south-1.amazonaws.com/353211646521/sales-report-queue
Email subscription: abhirvce@gmail.com
Lambda env var: SNS_TOPIC_ARN
```

## Step-by-Step Setup
1. Create S3 bucket `scj-sales-uploads`.
2. Create folder prefix `uploads/` for incoming CSV files.
3. Create SQS queue `sales-report-queue` with visibility timeout around 150 seconds.
4. Create DLQ `sales-report-dlq` and configure redrive policy with max receives = 3.
5. Add SQS access policy allowing S3 to send messages to the queue.
6. Create SNS topic `sales-report-notifications`.
7. Subscribe email address and confirm the subscription email.
8. Create Lambda `sales-report-generator` with required libraries/layer.
9. Add SQS trigger to Lambda.
10. Configure S3 event notification for `uploads/*.csv` to SQS.
11. Upload a CSV and validate the processing output.

## How to Run / Demo
```bash
aws s3 cp sales_data.csv s3://scj-sales-uploads/uploads/sales_data.csv --no-verify-ssl

aws sqs get-queue-attributes   --queue-url https://sqs.ap-south-1.amazonaws.com/353211646521/sales-report-queue   --attribute-names ApproximateNumberOfMessages   --no-verify-ssl
```

## What to Verify
- Queue message count returns to 0 after processing.
- CloudWatch Logs for `/aws/lambda/sales-report-generator` show file processing.
- Email report is received through SNS.
- DLQ remains empty for successful runs.

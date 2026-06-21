# Task 3: Static Website Hosting on S3

## What was built
- S3 bucket configured for static website hosting
- Index and error documents uploaded
- Bucket policy for public read access

## Key Commands
```bash
aws s3 mb s3://training-static-site-353211646521
aws s3 website s3://training-static-site-353211646521 \
  --index-document index.html --error-document error.html
aws s3 sync ./dist s3://training-static-site-353211646521
```

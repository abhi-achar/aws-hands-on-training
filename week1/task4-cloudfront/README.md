# Task 4: CloudFront CDN Distribution

## What was built
- CloudFront distribution fronting S3 bucket
- HTTPS with default CloudFront certificate
- Caching configured for static assets

## Architecture
Users -> CloudFront (Edge Locations) -> S3 Origin

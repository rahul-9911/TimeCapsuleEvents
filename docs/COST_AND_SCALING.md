# Serverless Architecture: Cost & Scaling Guide

This document breaks down the AWS Serverless architecture for SnapEvent, detailing exactly what runs during user interactions, how AWS bills for these resources, and cost estimates for different scales of usage.

## 1. What is Deployed (The Idle State)

When no one is using the site, the infrastructure costs almost **$0.00**. There are no idle servers or databases.

*   **API Gateway**: The HTTP front door. Billed per 1 million requests ($1.00 - $1.20).
*   **DynamoDB (Database)**: Configured in "On-Demand" mode. Holds events and access codes. Billed per Read/Write operation (fractions of a penny). No hourly charge.
*   **S3 Buckets**: Holds Terraform state, frontend code, and photos. Billed per GB stored per month (~$0.023/GB).
*   **ECR (Container Registry)**: Holds the `snapevent:latest` Docker image (~$0.10/GB/month).
*   **Lambda Functions (API & Cleanup)**: The core compute. Completely turned off until triggered.
*   **EventBridge Scheduler**: Hourly cron job trigger. Billed at $1.00 per 1 million invocations (virtually free).
*   **SES (Email)**: Billed at $0.10 per 1,000 emails sent.

---

## 2. Execution Lifecycles (What runs when)

Because we use **S3 Presigned URLs**, the Lambda function is completely bypassed for heavy file transfers.

### Flow A: Organiser Login
1. Organiser requests magic link.
2. **Lambda runs (1 time, ~300ms)**: Generates link, asks SES to send email, shuts down.
3. Organiser clicks link.
4. **Lambda runs (1 time, ~100ms)**: Validates token, sets session cookie.

### Flow B: Participant Views Gallery
1. Participant enters access code.
2. **Lambda runs (1 time, ~50ms)**: Validates code.
3. Participant requests photo list.
4. **Lambda runs (1 time, ~100ms)**: Queries DynamoDB, generates S3 Presigned GET URLs for all photos.
5. **Lambda DOES NOT RUN**: Browser downloads all images directly from S3.

### Flow C: Participant Uploads Photos
1. Participant selects 10 photos to upload.
2. **Lambda runs (1 time, ~50ms)**: Generates 10 S3 Presigned POST URLs (upload tickets).
3. **Lambda DOES NOT RUN**: Browser uploads the heavy binary files directly to S3.
4. **Lambda runs (10 times, ~30ms each)**: Browser hits the `/confirm` endpoint after each successful S3 upload to write the database record.

### Flow D: Hourly Cleanup
1. EventBridge triggers `cleanup` Lambda every hour.
2. **Lambda runs (1 time, ~200ms)**: Deletes expired events and their S3 photos.

---

## 3. Cost Estimates by Scale

AWS Lambda provides **1 Million free requests** and **400,000 GB-seconds** of compute time per month on the permanent Free Tier. In a serverless photo platform, **Compute (Lambda) and Database (DynamoDB) are practically free**. The primary cost driver is **Data Transfer Out (Bandwidth)** (First 100GB/mo free, then ~$0.09/GB).

### Tier 1: Low Usage (The "Side Project")
*Example: 10 events/month, 50 guests/event.*
*   **Storage**: Near $0 (events auto-delete after 24h).
*   **Compute/DB**: Fits entirely within AWS Free Tier.
*   **Bandwidth**: ~30GB total download. Fits entirely within 100GB Free Tier.
*   **Estimated Monthly Bill: $0.00 to $1.00**

### Tier 2: Medium Usage (The "Profitable SaaS")
*Example: 200 events/month, 150 guests/event (30,000 users/month).*
*   **Storage**: ~$1.15 (Average 50GB persistent storage).
*   **Compute (Lambda)**: Fits entirely within Free Tier!
*   **API Gateway & DynamoDB**: ~$2.00
*   **S3 Requests**: ~$0.80
*   **Bandwidth**: ~1,500 GB downloaded. (1,400 GB billable at $0.09). ~$126.00.
*   **Estimated Monthly Bill: ~$130.00** *(95% is bandwidth)*

### Tier 3: Massive Scale (The "Viral Hit")
*Example: 2,000 events/month, 500 guests/event (1,000,000 users/month).*
*   **Compute (Lambda/API Gateway)**: ~$20.00 (Exceeds free tier).
*   **Database (DynamoDB)**: ~$15.00
*   **S3 Requests**: ~$12.00
*   **Bandwidth**: ~50,000 GB (50 TB) downloaded. ~$4,500.00.
*   **Estimated Monthly Bill: ~$4,550.00**

---

## 4. Future Optimizations for Scale

If the platform approaches Tier 2 or Tier 3 usage, the following architectural additions are required to mitigate Data Transfer costs:

1. **Amazon CloudFront (CDN)**: Put CloudFront in front of the S3 bucket. CloudFront provides 1 Terabyte of free bandwidth per month, cheaper overage rates, and caches images geographically closer to users.
2. **Lambda Image Resizer (Thumbnails)**: Add an S3-triggered Lambda function that automatically generates a compressed, low-res thumbnail (e.g., 200KB) when a 5MB photo is uploaded. The gallery UI loads the cheap thumbnails, and only fetches the heavy original file if the user explicitly clicks "Download". This alone reduces bandwidth costs by 80-90%.

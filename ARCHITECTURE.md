# SnapEvent Architecture Overview

This document provides a deep dive into the serverless architecture of **SnapEvent (TimeCapsuleEvents)**.

## 1. Core Philosophy: Pure Serverless

SnapEvent was migrated from a containerized ECS/Fargate architecture to a pure serverless architecture to achieve **near-zero cost when idle**, high scalability, and minimal operational overhead.

- **Compute:** AWS Lambda via API Gateway HTTP API.
- **Database:** Amazon DynamoDB (Single-Table Design).
- **Storage:** Amazon S3 with Presigned URLs.
- **Background Tasks:** EventBridge Scheduler + Cleanup Lambda.
- **Email:** Amazon SES.

### Why this architecture?
1. **Zero Idle Cost:** If no one is using the application, the cost is effectively $0. You only pay per request (Lambda, API Gateway) and per read/write (DynamoDB On-Demand).
2. **Infinite Scaling:** Lambda automatically scales concurrently with incoming traffic. There is no need to worry about container scaling policies or CPU/Memory thresholds.
3. **No VPC Overhead:** By dropping RDS and EFS, the application no longer requires a VPC, NAT Gateways, or Application Load Balancers, drastically reducing base infrastructure costs and complexity.

---

## 2. Component Deep Dive

### 2.1 The Unified API (`services/api/`)
Built with **FastAPI** and wrapped by **Mangum** to run on AWS Lambda.
- **Routing:** All API Gateway traffic is proxied to a single Lambda function handling all routes (`/auth/*`, `/api/events/*`, `/e/{code}/photos/*`).
- **Data Layer (`db.py`):** Uses `boto3` to interact with DynamoDB. Replaces both the old PostgreSQL control plane database and the isolated SQLite event databases.
- **Authentication (`routers/auth.py`):** Passwordless magic-link authentication using SES. Generates a secure token stored with a TTL in DynamoDB. Clicking the link creates a session cookie.
- **Event Registry (`routers/events.py`):** Events are now just metadata records in DynamoDB. There is no longer a need to "spawn" or orchestrate containers. Events are instantly active upon creation.
- **Storage Layer (`storage.py`):** Uploads directly to S3. Generates short-lived AWS v4 Presigned URLs that allow the participant's browser to download/view images directly from S3. The Lambda function never streams image bytes through its own memory for downloads.

### 2.2 The Cleanup Lambda (`services/api/cleanup.py`)
- Scheduled via **Amazon EventBridge** to run every hour.
- Scans the DynamoDB table for events whose `expires_at` timestamp is in the past.
- Automatically purges all associated S3 photos and DynamoDB records for expired events, ensuring data privacy and minimizing storage costs.

### 2.3 The Frontend (`frontend/`)
Built with pure HTML/CSS and Vanilla JavaScript. No build step (React/Vue/Webpack) is used to keep the MVP simple.
- **Static Hosting:** Currently served by the FastAPI Lambda itself via `StaticFiles`.
- **`api.js`:** A lightweight wrapper around `fetch` that handles JSON parsing, error throwing, and cookie credentials.
- **Gallery (`gallery.html`):** Custom-built responsive image gallery. Uses Presigned URLs provided by the API to load images securely and efficiently.

---

## 3. Data Storage (DynamoDB Single-Table Design)

All application state is stored in a single DynamoDB table.

**Table Structure:**
- `PK` (Partition Key): The primary entity identifier (e.g., `ORG#user@email.com` or `EVENT#ABC123`).
- `SK` (Sort Key): The specific record type (e.g., `PROFILE`, `META`, `PHOTO#<uuid>`).
- `GSI1`: Used for reverse lookups (e.g., finding all events belonging to an organiser, or resolving a session token).

**Item Types:**
1. **Organiser Profile:** `PK = ORG#<email>`, `SK = PROFILE`
2. **Auth Token:** `PK = ORG#<email>`, `SK = AUTHTOKEN#<token>` (Uses native DynamoDB TTL)
3. **Session:** `PK = ORG#<email>`, `SK = SESSION#<token>` (Uses native DynamoDB TTL)
4. **Event Metadata:** `PK = EVENT#<event_code>`, `SK = META`
5. **Access Code:** `PK = EVENT#<event_code>`, `SK = ACCESS#<code>`
6. **Photo:** `PK = EVENT#<event_code>`, `SK = PHOTO#<photo_id>`
7. **Activity Log:** `PK = EVENT#<event_code>`, `SK = LOG#<timestamp>#<id>`

---

## 4. Production Checklist (Future Work)

Before launching this MVP to thousands of real users, consider these enhancements:

1. **CloudFront Distribution:** Currently, static assets (HTML/CSS/JS) are served by the Lambda function. Moving them to an S3 bucket behind CloudFront will reduce Lambda invocations, lower latency, and decrease costs.
2. **Rate Limiting:** Protect the `/auth/request` endpoint against email bombing. API Gateway usage plans or AWS WAF can provide this protection.
3. **Custom Domain:** Configure API Gateway with a custom domain name and ACM certificate.
4. **Secrets Management:** Ensure SES sender emails and other sensitive config are securely managed via SSM Parameter Store or Secrets Manager in the production environment.

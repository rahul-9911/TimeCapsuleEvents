# TimeCapsuleEvents (SnapEvent)

> **Event-based photo sharing — simple, isolated, and scalable.**
> A 100% serverless platform where organisers create events and distribute access codes.
> Participants join with a code and view, upload, or delete photos based on their
> permission level. No accounts needed for participants. Cost-optimized for AWS.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture Overview](#architecture-overview) (See also [ARCHITECTURE.md](ARCHITECTURE.md))
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [How to Use the App](#how-to-use-the-app)
- [AWS Deployment (Terraform)](#aws-deployment-terraform)
- [Makefile Reference](#makefile-reference)

---

## What It Does

**For organisers:**
- Sign in with just your email (magic link — no password)
- Create events (birthday, wedding, corporate, etc.)
- Generate individual access codes for each guest/group
- Three permission levels per code: View Only / View & Upload / Full Access
- See exactly who accessed what, when, and with which code
- Revoke any code at any time
- **Auto-Expiry:** Events auto-delete after 24 hours to save storage costs.

**For participants:**
- Enter your code at the event URL
- Browse photos in an optimized thumbnail gallery (400px JPEG thumbnails, saving bandwidth)
- Upload photos up to 40MB each (batch uploads up to 200 files with 5x concurrency & 3x retries)
- Automatic deduplication (skips re-uploading files that already exist in the event)
- Detailed upload summary showing success, skipped duplicates, and per-file S3 error messages
- Delete photos (if your code permits)
- View or download full-resolution photos securely via S3 Presigned URLs

---

## Architecture Overview

```text
                        Browser
                           │
                    ┌──────▼──────┐
                    │ API Gateway │  ← HTTP API (AWS)
                    └──────┬──────┘
                           │
                    ┌──────▼─────────────────┐
                    │   AWS Lambda (API)     │  FastAPI + Mangum
                    │                        │
                    │  /auth/*    → auth     │
                    │  /api/*     → events   │
                    │  /e/{code}  → photos   │
                    └──────┬─────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
  ┌───────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
  │   DynamoDB   │  │ Amazon S3   │  │ Amazon SES  │
  │ Single-Table │  │ Photos      │  │ Magic Links │
  └──────────────┘  └─────────────┘  └─────────────┘
          ▲                ▲
          │                │
  ┌───────┴────────────────┴──────┐
  │ AWS Lambda (Cleanup)          │  ← Hourly EventBridge Trigger
  └───────────────────────────────┘
```

**Key design principle:** 100% Serverless. No VPCs, no NAT Gateways, no idle RDS databases. You pay strictly for usage, achieving near-zero idle costs.

For a deep dive into the single-table DynamoDB design and data lifecycle, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Routing | API Gateway (HTTP API) |
| Compute | AWS Lambda (Python 3.12, Container Image) |
| Web Framework | FastAPI + Mangum + Pillow (Thumbnail generation) |
| Database | Amazon DynamoDB (On-Demand, Single-Table) |
| Object Storage | Amazon S3 (Originals + `thumbs/` 400px JPEGs) |
| Email | Amazon SES |
| Background Jobs | Amazon EventBridge Scheduler |
| AI Processing Worker | ComfyUI + Python Client Worker (`services/comfy-worker`) |
| IaC | Terraform (S3 native state locking) |
| Frontend | Vanilla HTML/CSS/JS (Concurrency pool upload, graceful thumbnail fallback) |

---

## Project Structure

```text
TimeCapsuleEvents/
│
├── services/
│   ├── api/                   # Core backend application
│   │   ├── main.py            # FastAPI app + Mangum Lambda handler
│   │   ├── cleanup.py         # Hourly EventBridge Lambda handler
│   │   ├── db.py              # DynamoDB operations
│   │   ├── storage.py         # S3 operations (presigned URLs)
│   │   ├── mailer.py          # SES email sending
│   │   ├── middleware.py      # Session auth
│   │   ├── models.py          # Pydantic schemas
│   │   └── routers/           # API routes
│   │
│   └── comfy-worker/          # Async ComfyUI AI processing worker
│       ├── main.py            # Polling loop & worker engine
│       ├── comfy_client.py    # ComfyUI REST/WebSocket client
│       ├── api_client.py      # SnapEvent Cloud API client
│       ├── s3_client.py       # S3 image downloader & uploader
│       └── workflows/         # ComfyUI API format workflow JSON files
│
├── frontend/                  # Plain HTML/CSS/JS (no build step)
│   ├── login.html             # Organiser login
│   ├── dashboard.html         # Organiser event list
│   ├── event-manage.html      # Event detail + code management
│   ├── gallery.html           # Photo gallery
│   └── js/api.js
│
├── terraform/
│   ├── modules/               # Reusable serverless modules
│   │   ├── api-gateway/
│   │   ├── dynamodb/
│   │   ├── ecr/
│   │   ├── lambda/
│   │   ├── ses/
│   │   └── storage/
│   └── environments/
│       ├── dev/               # Dev AWS environment composing the modules
│       └── staging/           # Staging AWS environment
│
├── Dockerfile                 # Lambda container image definition
├── Makefile                   # Build/push/deploy shortcuts
├── .env.example               # Environment variables
├── ARCHITECTURE.md
└── README.md
```

---

## ComfyUI AI Worker Setup & Running

The ComfyUI worker runs locally alongside ComfyUI, polling the API Gateway for queued jobs, downloading source photos from S3, processing them, and uploading enhanced outputs.

For full worker documentation, see [services/comfy-worker/README.md](file:///home/rahul/projects/facerecog/services/comfy-worker/README.md).

### 1. How to Run the Worker

```bash
cd services/comfy-worker
./venv/bin/python main.py
```

To run continuously in the background:
```bash
cd services/comfy-worker
nohup ./venv/bin/python main.py > worker.log 2>&1 &
```

### 2. Editing Variables (`services/comfy-worker/.env`)

Edit `services/comfy-worker/.env` to adjust configuration:

- **API Endpoint & Keys**:
  - `SNAPEVENT_API_URL`: Base URL of API Gateway (e.g. `https://your-api.execute-api.region.amazonaws.com`)
  - `WORKER_API_KEY`: Key matching `WORKER_API_KEY` on Lambda.
  - `S3_BUCKET`: Target S3 bucket name (e.g. `snapevent-dev-photos`)
- **ComfyUI Local Address**:
  - `COMFYUI_URL`: Local server address (`http://localhost:8188`)
- **Polling Frequency & Timeouts**:
  - `POLL_INTERVAL_SECONDS`: API queue polling frequency in seconds (default: `30`).
  - `COMFY_POLL_INTERVAL`: ComfyUI prompt status polling frequency in seconds (default: `3.0`).
  - `COMFY_TIMEOUT`: Timeout per image in seconds (default: `600.0`).

### 3. Adding or Changing Workflows

To add a new workflow to both local worker and cloud UI:

1. **Place JSON File**: Copy or export your workflow JSON into `services/comfy-worker/workflows/my_new_workflow.json`.
2. **Register in Worker (`services/comfy-worker/main.py`)**:
   ```python
   WORKFLOW_FILES: dict[str, str] = {
       "seedvr2_upscale": "seedvr2_upscale.json",
       "flux2_klein_detailer": "flux2_klein_detailer.json",
       "my_new_workflow": "my_new_workflow.json",  # <-- Add here
   }
   ```
3. **Register in API Backend (`services/api/routers/ai.py`)**:
   ```python
   AVAILABLE_WORKFLOWS: dict[str, str] = {
       "seedvr2_upscale": "SeedVR2 4x Upscale",
       "flux2_klein_detailer": "Flux2-Klein Image Detailer Best",
       "my_new_workflow": "My New Workflow Display Name",  # <-- Add here
   }
   ```
4. **Add Dropdown Option in Frontend (`frontend/event-manage.html`)**:
   ```html
   <select id="ai-workflow-select" style="width:100%;max-width:320px;">
     <option value="seedvr2_upscale">SeedVR2 4x Upscale</option>
     <option value="flux2_klein_detailer">Flux2-Klein Image Detailer Best</option>
     <option value="my_new_workflow">My New Workflow Display Name</option>
   </select>
   ```
5. **Restart Local Worker**:
   ```bash
   cd services/comfy-worker
   ./venv/bin/python main.py
   ```
6. **Deploy Updates Online to AWS Lambda**:
   ```bash
   make update-lambda env=dev TAG=v4
   ```

---

## How to Use the App

### Organiser Flow

1. **Sign in**: Go to the API Gateway URL, enter your email, and receive a magic link via SES.
2. **Create Event**: Click "+ New Event". It is instantly active.
3. **Generate Codes**: Create access codes for participants with specific permission levels.
4. **Monitor**: Watch live activity (views, uploads) directly from the dashboard.

### Participant Flow

1. **Join**: Open the share link and enter the access code.
2. **Interact**: View, download, or upload photos directly to S3 via presigned URLs.

---

## AWS Deployment (Terraform)

Deploying this architecture to a fresh AWS account requires a few initial setup steps, including creating a Terraform state bucket and handling a one-time "chicken-and-egg" deployment for the ECR registry and Lambda.

### Step 1: AWS CLI & IAM Setup
1. Log into your AWS Console and go to **IAM** -> **Users**.
2. Create a new user (e.g., `terraform-admin`) and attach the **AdministratorAccess** policy.
3. Generate **Access Keys** (CLI) for this user.
4. Install the [AWS CLI](https://aws.amazon.com/cli/) and configure it locally:
   ```bash
   aws configure
   ```
   *(Enter your Access Key, Secret Key, and preferred region, e.g., `us-east-1`)*

### Step 2: Create Terraform State Bucket
Terraform needs an S3 bucket to store its state file. Create this using the CLI (change the region and bucket name if desired):
```bash
aws s3 mb s3://snapevent-terraform-state --region us-east-1
```
*(If you change the bucket name, ensure you update `terraform/environments/dev/main.tf` to match).*

### Step 3: Configure Environment Variables
1. **SES Sender Email:** AWS SES starts in "Sandbox" mode. You must configure the email address that will send the magic links.
2. Edit `terraform/environments/dev/terraform.tfvars`:
   ```hcl
   ses_sender_email = "your.email@example.com"
   aws_region       = "us-east-1"
   ```
3. Copy `.env.example` to `.env` and ensure `SES_SENDER_EMAIL` matches:
   ```bash
   cp .env.example .env
   ```

### Step 4: The 3-Stage Initial Deployment
AWS Lambda requires a Docker image to exist in ECR before it can be created. However, Terraform creates the ECR registry. We break this loop in 3 steps:

**1. Initialize Terraform & Deploy ONLY the ECR Registry:**
```bash
cd terraform/environments/dev
terraform init
terraform apply -target=module.ecr -target=output.ecr_repository
```

**2. Build & Push the Code:**
Return to the root directory and use the Makefile to push the image to the new registry.
```bash
cd ../../../
make push env=dev
```

**3. Deploy the Rest of the Infrastructure:**
```bash
cd terraform/environments/dev
terraform apply
```
*(This creates DynamoDB, S3, API Gateway, and the Lambdas).*

### Step 5: Verify Your Email (AWS SES)
During the final apply, AWS will send a verification email to the `ses_sender_email` you specified. **You must click the link in that email.**
*Note: Because your account is in the SES Sandbox, you can only send emails TO verified addresses as well. Verify any email you want to log in with via the AWS Console, or request Production Access from AWS Support to send to anyone.*

### Step 6: Access the App
Run `terraform output api_url` to get your API Gateway URL. Open it in your browser, enter your verified email, and check your inbox for the magic link!

---

### Quick Application Updates
If you only changed Python or HTML/JS code (no infrastructure changes), you can fast-update the Lambda functions:
```bash
make update-lambda env=dev TAG=v2
```

---

## Makefile Reference

```bash
make build              # Build Lambda Docker image
make push TAG=v1        # Build + push to ECR
make update-lambda      # Push image + trigger Lambda function updates

make init env=dev       # Initialize Terraform
make plan env=dev       # Preview Terraform changes
make deploy env=dev     # Push image + Apply Terraform
make destroy env=dev    # Tear down all infrastructure
make outputs env=dev    # Show Terraform outputs
```

---

## Licence

MIT

# TimeCapsuleEvents (SnapEvent)

> **Event-based photo sharing — simple, isolated, and portable.**
> Each event gets its own independent container. Organisers create events and distribute
> access codes. Participants join with a code and view, upload, or delete photos based
> on their permission level. No accounts needed for participants.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Local Development Setup](#local-development-setup)
- [How to Use the App](#how-to-use-the-app)
- [Access Code Permissions](#access-code-permissions)
- [Enabling Real Email (Gmail)](#enabling-real-email-gmail)
- [AWS Deployment (Terraform)](#aws-deployment-terraform)
- [Makefile Reference](#makefile-reference)
- [Roadmap](#roadmap)

---

## What It Does

**For organisers:**
- Sign in with just your email (magic link — no password)
- Create events (birthday, wedding, corporate, etc.)
- Generate individual access codes for each guest/group
- Three permission levels per code: View Only / View & Upload / Full Access
- See exactly who accessed what, when, and with which code
- Revoke any code at any time

**For participants:**
- Enter your code at the event URL
- Browse all photos in a gallery
- Upload your own photos (if your code permits)
- Delete photos (if your code permits)
- Download any photo

**No face recognition yet** — that's Phase 2.

---

## Architecture Overview

```
                        Browser
                           │
                    ┌──────▼──────┐
                    │  Traefik    │  ← local ALB (prod: AWS ALB)
                    └──────┬──────┘
                           │
                    ┌──────▼───────────────┐
                    │   Control Plane      │  always running
                    │   FastAPI + Postgres │
                    │                      │
                    │  /auth/*  → auth     │
                    │  /api/*   → events   │
                    │  /e/{code}→ proxy ──►│──► Event Container
                    └──────────────────────┘
                                               ┌─────────────────┐
                                               │  Event-ABC123   │  one per event
                                               │  FastAPI+SQLite │
                                               │  /data/event.db │
                                               └────────┬────────┘
                                                        │
                                               ┌────────▼────────┐
                                               │  MinIO / S3     │
                                               │  photos bucket  │
                                               └─────────────────┘
```

**Key design principle:** Each event = its own isolated Fargate task (or Docker container locally).
The control plane spawns and manages them. 100 events = 100 containers.

---

## Tech Stack

| Component | Local Dev | AWS (Prod) |
|-----------|-----------|------------|
| Reverse proxy | Traefik | ALB |
| Control plane | FastAPI + asyncpg | ECS Fargate |
| Event worker | FastAPI + aiosqlite | ECS Fargate (Spot) |
| Database (control) | PostgreSQL (Docker) | RDS PostgreSQL |
| Event data | SQLite on Docker volume | SQLite on EFS |
| Object storage | MinIO | S3 |
| Email | Console output | Gmail SMTP / SES |
| Container spawning | Docker SDK | ECS RunTask |
| IaC | — | Terraform |

---

## Project Structure

```
TimeCapsuleEvents/
│
├── services/
│   ├── control/               # Control plane (always-on service)
│   │   ├── main.py            # FastAPI app, event proxy
│   │   ├── db.py              # PostgreSQL connection + schema
│   │   ├── email.py           # Magic link sender (console or Gmail)
│   │   ├── middleware.py      # Session auth dependency
│   │   ├── models.py          # Pydantic schemas
│   │   ├── spawner.py         # Spawns event containers (Docker/ECS)
│   │   └── routers/
│   │       ├── auth.py        # POST /auth/request, GET /auth/verify
│   │       ├── events.py      # Event CRUD
│   │       ├── codes.py       # Access code management
│   │       └── participant.py # Code → event discovery endpoint
│   │
│   └── event/                 # Event worker (one instance per event)
│       ├── main.py            # FastAPI app
│       ├── db.py              # SQLite (isolated per event)
│       ├── storage.py         # S3/MinIO photo upload/delete
│       ├── models.py          # Pydantic schemas
│       └── routers/
│           └── public.py      # Participant + internal endpoints
│
├── frontend/                  # Plain HTML/CSS/JS (no build step)
│   ├── login.html             # Organiser login
│   ├── dashboard.html         # Organiser event list
│   ├── event-manage.html      # Event detail + code management
│   ├── join.html              # Participant code entry
│   ├── gallery.html           # Photo gallery
│   ├── css/style.css
│   └── js/api.js
│
├── docker/
│   ├── control/Dockerfile
│   └── event/Dockerfile
│
├── terraform/
│   ├── modules/               # Reusable modules (DRY)
│   │   ├── networking/        # VPC, ALB, security groups
│   │   ├── ecs-cluster/       # ECS cluster, IAM, ECR
│   │   ├── storage/           # S3 bucket, EFS filesystem
│   │   ├── control-plane/     # Control plane ECS service + RDS
│   │   └── event-worker/      # Event task definition template
│   └── environments/
│       ├── dev/               # Dev AWS environment
│       ├── staging/           # Staging AWS environment
│       └── prod/              # Production AWS environment
│
├── docker-compose.yml         # Local full-stack (Traefik + Postgres + MinIO)
├── Makefile                   # Dev/build/push/deploy shortcuts
├── .env.example               # Environment variable template
└── README.md
```

---

## Local Development Setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose v2
- Git

### Steps

**1. Clone the repo**
```bash
git clone https://github.com/rahul-9911/TimeCapsuleEvents.git
cd TimeCapsuleEvents
```

**2. Create your `.env` file**
```bash
cp .env.example .env
```
The defaults work out of the box for local dev — no changes needed to start.

**3. Build the event worker image**

The control plane spawns event containers dynamically, so the image must exist on the
host before the first event is created:
```bash
docker build -t snapevent-event:latest -f docker/event/Dockerfile .
```

**4. Start the stack**
```bash
docker compose up --build
```

This starts:
- **Traefik** (reverse proxy) → http://localhost
- **Control Plane** (FastAPI) → proxied through Traefik
- **PostgreSQL** → internal, port 5432
- **MinIO** (S3-compatible storage) → console at http://localhost:9001
- **MinIO init** → creates the `snapevent-dev` bucket automatically

> ⏱ First run downloads images and installs Python packages — takes ~2 minutes.
> Subsequent starts are fast (images are cached).

**5. Open the app**

| URL | What it is |
|-----|-----------|
| http://localhost | Login page |
| http://localhost/dashboard.html | Organiser dashboard |
| http://localhost:8080 | Traefik dashboard (routing overview) |
| http://localhost:9001 | MinIO console (storage browser) |

---

## How to Use the App

### Organiser Flow

**Step 1 — Sign in**
1. Go to http://localhost
2. Enter any email address → click **Send magic link**
3. Since SMTP is not configured by default, the link prints to the **Docker logs**:
   ```bash
   docker compose logs control | grep "MAGIC LINK" -A 5
   ```
4. Copy the link from the logs and open it in your browser
5. You'll land on the dashboard

**Step 2 — Create an event**
1. Click **+ New Event**
2. Fill in the event name (e.g. "Sarah's Birthday"), optional description and date
3. Click **Create Event**
4. You'll be redirected to the event management page
5. Wait a few seconds for the event container to start (status changes from `STARTING` → `RUNNING`)

**Step 3 — Create access codes**
1. On the event management page, click **+ Create Code**
2. Optionally label it (e.g. "Uncle Bob", "Press", "Table 5")
3. Choose the permission level:
   - **View Only** — can browse and download
   - **View & Upload** — can also add photos
   - **Full Access** — can view, upload, and delete
4. Click **Generate Code**
5. Copy the share link or the 8-char code — send it to the participant

**Step 4 — Monitor activity**
- Back on the event page you can see for each code: views, uploads, deletes, last seen
- Click **Revoke** on any code to cut off that participant's access instantly

---

### Participant Flow

**Step 1 — Join the event**
1. Open the share link you received (e.g. `http://localhost/join.html`)
2. Enter your access code
3. Click **Access Event**

**Step 2 — View photos**
- You'll see the photo gallery
- Click any photo to view it full size
- Click **↓ Download** in the lightbox to save it

**Step 3 — Upload photos** *(if your code allows)*
- Click **↑ Upload Photos** in the toolbar
- Select one or more images
- They upload with a progress indicator

**Step 4 — Delete photos** *(if your code allows)*
- Hover over a photo → click **Delete**
- Or open in lightbox → click **Delete**

---

## Access Code Permissions

| Permission | View | Upload | Delete |
|------------|:----:|:------:|:------:|
| `VIEW_ONLY` | ✅ | ❌ | ❌ |
| `VIEW_UPLOAD` | ✅ | ✅ | ❌ |
| `VIEW_UPLOAD_DELETE` | ✅ | ✅ | ✅ |

Each code is unique and independently revocable. You can create as many codes as you want —
one per person if needed — so you always know who did what.

---

## Enabling Real Email (Gmail)

When you're ready to send real magic links by email:

1. **Create a Gmail App Password:**
   - Go to https://myaccount.google.com/apppasswords
   - App: Mail → Device: Other → name it `SnapEvent`
   - Copy the 16-character password

2. **Update your `.env`:**
   ```env
   SMTP_USER=your-actual-gmail@gmail.com
   SMTP_PASS=abcd efgh ijkl mnop   # the 16-char app password (spaces ok)
   SMTP_FROM=your-actual-gmail@gmail.com
   ```

3. **Restart the control plane:**
   ```bash
   docker compose restart control
   ```

Magic links will now be sent to the organiser's email automatically.

---

## AWS Deployment (Terraform)

### Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform ≥ 1.6 installed
- Docker images pushed to ECR

### One-time setup (remote state)
```bash
# Create S3 bucket and DynamoDB table for Terraform state
aws s3 mb s3://snapevent-terraform-state
aws dynamodb create-table \
  --table-name snapevent-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

### Deploy to staging
```bash
# Build and push images to ECR (creates ECR repos if they don't exist yet)
make deploy env=staging TAG=v1.0

# Or step by step:
make build TAG=v1.0
make push  TAG=v1.0
cd terraform/environments/staging
terraform init
terraform apply -var="image_tag=v1.0" -var="smtp_user=you@gmail.com" -var="smtp_pass=xxxx"
```

### Deploy to prod
```bash
make deploy env=prod TAG=v1.0 \
  TF_VAR_domain_name=yourdomain.com \
  TF_VAR_smtp_user=you@gmail.com \
  TF_VAR_smtp_pass=xxxx
```

### What Terraform creates

| Resource | Dev/Staging | Prod |
|----------|-------------|------|
| VPC + subnets | ✅ | ✅ |
| ALB | ✅ | ✅ |
| ECS Cluster (Fargate Spot) | ✅ | ✅ |
| ECR repos (control + event) | ✅ | ✅ |
| RDS PostgreSQL | t3.micro | t3.medium |
| EFS (event SQLite storage) | ✅ | ✅ |
| S3 bucket | 30-day expiry | 365-day expiry |
| Secrets Manager | ✅ | ✅ |
| CloudWatch Logs | ✅ | ✅ |

### Estimated AWS costs (MVP scale)

| Component | Cost |
|-----------|------|
| Control plane (Fargate, always on) | ~$18/month |
| Event containers (Fargate Spot, per event) | ~$1–2/month per active event |
| RDS t3.micro | ~$15/month |
| EFS (minimal data) | ~$0.30/GB/month |
| S3 + data transfer | ~$1–5/month |
| **10 active events total** | **~$50–60/month** |

---

## Makefile Reference

```bash
make dev          # Start full local stack (docker compose up --build)
make dev-down     # Stop and remove all containers + volumes
make logs         # Tail control plane logs
make shell        # Shell into the running control container

make build        # Build both Docker images locally
make push TAG=v1  # Build + push to ECR (requires AWS login)
make deploy env=staging TAG=v1  # Push + terraform apply
make plan   env=staging TAG=v1  # Preview changes (no apply)
make destroy env=staging        # Tear down all infrastructure
```

---

## Roadmap

### Phase 1 — MVP (current)
- [x] Organiser magic link auth
- [x] Event creation + management
- [x] Per-code access control (view / upload / delete)
- [x] Photo upload + gallery + lightbox
- [x] Activity tracking per code
- [x] Per-event isolated containers
- [x] IaC (Terraform, 3 environments)
- [x] Local dev (Docker Compose)

### Phase 2 — Face Recognition
- [ ] Participant uploads selfie → sorted gallery (only their photos)
- [ ] InsightFace on self-hosted / AWS Rekognition on cloud
- [ ] Face embedding stored in pgvector

### Phase 3 — Monetisation
- [ ] Stripe integration (per-event pricing)
- [ ] Free tier limits (100 photos, 3-day TTL)
- [ ] Paid tiers (500 / 2000 / unlimited photos)

### Phase 4 — Enhancements
- [ ] QR code generation for event codes
- [ ] Custom event branding (logo, background)
- [ ] Video/slideshow export
- [ ] Photo upscaling (Real-ESRGAN)
- [ ] Email notifications to participants
- [ ] CI/CD pipeline (GitHub Actions)

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit: `git commit -m "feat: description"`
4. Push: `git push origin feat/your-feature`
5. Open a Pull Request

---

## Licence

MIT

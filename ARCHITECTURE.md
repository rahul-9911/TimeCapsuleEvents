# SnapEvent Architecture Overview

This document provides a deep dive into the architecture of **SnapEvent (TimeCapsuleEvents)** as built so far. It is intended for developers picking up the project in the future.

## 1. Core Philosophy: The "Event Worker" Pattern

Unlike traditional monolithic web applications where all traffic is handled by a single backend connected to a shared database, SnapEvent uses a **Control Plane + Event Worker** architecture.

- **Control Plane:** An always-on, lightweight service that handles Organiser authentication (magic links), payment/subscription status, and event creation.
- **Event Worker:** A completely isolated container spawned **per event**. When an organiser creates an event, the Control Plane provisions a brand new container specifically for that event. All participant traffic (guests viewing/uploading photos) routes directly to this isolated container.

### Why this architecture?
1. **Total Isolation:** Code executing for Event A has absolutely no access to the data or database of Event B.
2. **Cost Efficiency (Scale-to-zero):** In production (AWS ECS Fargate), event containers can automatically shut down when no participants are active, saving significant compute costs. The control plane wakes them up on the first incoming request.
3. **Portability:** Each event's data is fully encapsulated (one SQLite file + one S3 prefix). Archiving, deleting, or moving an event is trivial.

---

## 2. Component Deep Dive

### 2.1 The Control Plane (`services/control/`)
Built with **FastAPI** and **asyncpg** (PostgreSQL).
- **Authentication (`routers/auth.py`):** Passwordless magic-link authentication. Generates a secure token and emails it to the user. Clicking the link exchanges the token for a long-lived (30-day) HTTP-only session cookie.
- **Event Registry (`routers/events.py`):** Maintains a central registry of all events, their unique 6-character codes, and their container statuses (STARTING, RUNNING, ERROR, STOPPED).
- **Spawner (`spawner.py`):** Abstracts the container orchestration. Locally, it uses the Docker SDK to spin up containers on the local machine. In production, it uses `boto3` to trigger AWS ECS `RunTask` API calls for Fargate Spot containers.
- **Reverse Proxy Routing:** The Control Plane container acts as a central hub but *relies on Traefik/ALB* for actual traffic routing. It assigns Traefik labels (or AWS ALB Listener Rules) to the newly spawned containers so traffic to `/e/{event_code}/*` hits the correct worker.

### 2.2 The Event Worker (`services/event/`)
Built with **FastAPI** and **aiosqlite** (SQLite).
- **Data Isolation:** Each worker mounts the shared EFS volume but explicitly connects to an isolated SQLite file named `{EVENT_CODE}_event.db`. 
- **Storage (`storage.py`):** Abstracted via `boto3`. Uploads images to MinIO (dev) or S3 (prod) under the prefix `events/{EVENT_CODE}/`.
- **Presigned URLs:** The worker never streams image bytes through its own memory. It generates short-lived AWS v4 Presigned URLs that allow the participant's browser to download images directly from S3/MinIO.
- **Participant Access (`routers/public.py`):** Validates the `X-Participant-Code` header against the SQLite database to enforce Role-Based Access Control (VIEW_ONLY, VIEW_UPLOAD, VIEW_UPLOAD_DELETE).

### 2.3 The Frontend (`frontend/`)
Built with pure HTML/CSS and Vanilla JavaScript. No build step (React/Vue/Webpack) is used to keep the MVP incredibly simple, fast, and easy to modify.
- **`api.js`:** A lightweight wrapper around `fetch` that handles JSON parsing, error throwing, and cookie credentials.
- **Polling (`dashboard.html`):** Since containers take 10-20 seconds to boot on ECS, the dashboard automatically polls the Control Plane to update the UI when the container transitions from `STARTING` to `RUNNING`.
- **Lightbox Navigation (`gallery.html`):** Custom-built responsive image gallery with arrow-key navigation and direct download enforcement (via `Content-Disposition` S3 headers).

---

## 3. Data Lifecycle & Storage

1. **Creation:** When an event is created, a record is added to PostgreSQL. The Event Worker starts, initializes its SQLite tables on the EFS mount, and waits for traffic.
2. **Usage:** Participants upload files. The Worker generates a unique UUID, uploads to S3, and saves the S3 key + UUID to SQLite.
3. **Deletion (Garbage Collection):** When an organiser deletes an event, the Control Plane forcefully stops the worker, deletes the PostgreSQL registry entry, deletes the `{EVENT_CODE}_event.db` file from EFS, and triggers a recursive AWS S3 deletion of all photos under that event's prefix. No data is orphaned.

---

## 4. Production Checklist (Future Work)

Before launching this MVP to thousands of real users, the following architectural gaps identified during the last development session should be addressed:

1. **Scale-to-Zero Implementation:** Currently, event containers run forever. Implement a watchdog inside the event worker that exits the container after 30 minutes of zero HTTP requests. The Control Plane must then be updated to catch HTTP 502/404 errors for sleeping events and buffer the request while it re-spawns the container.
2. **Resource Limits:** Docker/ECS tasks should have strict memory ceilings (e.g., `256MB`) to prevent a malicious user from causing Out-Of-Memory (OOM) host crashes.
3. **Rate Limiting:** Protect the `/auth/request` endpoint against email bombing using Redis or a simple PostgreSQL-based rate limiting table.
4. **Graceful Shutdown:** Handle `SIGTERM` in the FastAPI workers to safely close SQLite connections rather than abrupt termination.
5. **Secrets Management:** Replace environment-variable-based credentials with AWS Secrets Manager or ECS Task Execution Roles.

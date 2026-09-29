# SnapEvent ComfyUI Worker

> **Asynchronous AI Image Processing Engine for SnapEvent**
> Polls the SnapEvent Cloud API Gateway for queued image processing jobs, executes custom workflows using a local ComfyUI instance, and uploads processed results directly back to Amazon S3.

---

## Architecture & Flow

```text
┌──────────────────────┐        1. Poll Queue       ┌───────────────────────┐
│                      │ ◄───────────────────────── │                       │
│  SnapEvent API       │                            │  ComfyUI Worker       │
│  (AWS Lambda/Gateway)│ ─────────────────────────► │  (Local Python App)   │
│                      │        2. Claim Job        │                       │
└──────────┬───────────┘                            └───────────┬───────────┘
           │                                                    │
 3. Fetch  │                                        4. Submit   │ 5. Export
 Photos    │                                        Workflow    │ Result
           ▼                                                    ▼
┌──────────────────────┐                            ┌───────────────────────┐
│  Amazon S3 Bucket    │ ◄───────────────────────── │  Local ComfyUI Engine │
│  (Source & Output)   │        6. Upload Result    │  (http://localhost:8188)│
└──────────────────────┘                            └───────────────────────┘
```

1. **Poll Queue**: Worker queries `GET /api/ai/worker/queue` using the static `X-Worker-Api-Key`.
2. **Claim Job**: Claims the job via `POST /api/ai/worker/jobs/{job_id}/claim` (moves job status from `QUEUED` to `PROCESSING`).
3. **Fetch & Download**: Downloads source photos from the S3 bucket to local temp storage.
4. **ComfyUI Workflow**: Sends prompt JSON payload to ComfyUI API endpoint (`http://localhost:8188/prompt`).
5. **Poll ComfyUI History**: Polls `http://localhost:8188/history/{prompt_id}` until execution finishes.
6. **Upload & Progress Report**: Uploads generated images to S3 and calls `POST /api/ai/worker/jobs/{source_event}/{job_id}/progress` to update DynamoDB state.

---

## Prerequisites

1. **Local ComfyUI**: Must be installed and running locally with API access enabled (default `http://localhost:8188`).
2. **Python 3.10+**: Virtual environment with dependencies installed:
   ```bash
   cd services/comfy-worker
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **AWS CLI Credentials**: Configured locally with access to the target S3 bucket:
   ```bash
   aws configure
   ```

---

## Environment Variables Configuration

Create or edit `services/comfy-worker/.env`:

```ini
# ── API & Cloud Setup ─────────────────────────────────────────────────────────
SNAPEVENT_API_URL=https://your-api-gateway-url.execute-api.ap-south-1.amazonaws.com
WORKER_API_KEY=your_secure_worker_api_key
S3_BUCKET=snapevent-dev-photos
AWS_REGION=ap-south-1

# ── Local ComfyUI Engine ──────────────────────────────────────────────────────
COMFYUI_URL=http://localhost:8188
COMFYUI_INPUT_DIR=/home/rahul/comfy/ComfyUI/input
COMFYUI_OUTPUT_DIR=/home/rahul/comfy/ComfyUI/output

# ── Polling & Timeout Tuning ──────────────────────────────────────────────────
POLL_INTERVAL_SECONDS=30
COMFY_POLL_INTERVAL=3.0
COMFY_TIMEOUT=600.0

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
```

### Environment Variables Reference

| Variable | Description | Default |
|---|---|---|
| `SNAPEVENT_API_URL` | Base URL of the deployed SnapEvent API Gateway (no trailing slash) | *Required* |
| `WORKER_API_KEY` | Static API key matching `WORKER_API_KEY` on Lambda environment | *Required* |
| `S3_BUCKET` | Amazon S3 bucket name storing source and processed event photos | *Required* |
| `AWS_REGION` | AWS Region for S3 bucket operations | `ap-south-1` |
| `COMFYUI_URL` | Base URL where local ComfyUI is listening | `http://localhost:8188` |
| `COMFYUI_INPUT_DIR` | Absolute path to ComfyUI's `input/` folder | `/home/rahul/comfy/ComfyUI/input` |
| `COMFYUI_OUTPUT_DIR` | Absolute path to ComfyUI's `output/` folder | `/home/rahul/comfy/ComfyUI/output` |
| `POLL_INTERVAL_SECONDS` | Interval in seconds between polling SnapEvent API for new jobs | `30` |
| `COMFY_POLL_INTERVAL` | Interval in seconds for polling ComfyUI completion status | `3.0` |
| `COMFY_TIMEOUT` | Max timeout in seconds for a single image before failing | `600.0` |
| `LOG_LEVEL` | Logging detail (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

## How to Run the Worker

### 1. Interactive Run (Foreground)

To run interactively in terminal and view real-time execution logs:

```bash
cd services/comfy-worker
./venv/bin/python main.py
```

### 2. Background Task (No-hangup)

To run continuous polling in the background:

```bash
cd services/comfy-worker
nohup ./venv/bin/python main.py > worker.log 2>&1 &
```

View background logs:
```bash
tail -f worker.log
```

---

## Managing & Changing Workflows

Workflows are defined as ComfyUI API JSON format files located in `services/comfy-worker/workflows/`.

### Available Workflows

- `seedvr2_upscale`: `seedvr2_upscale.json` (SeedVR2 4x Upscale)
- `flux2_klein_detailer`: `flux2_klein_detailer.json` (Flux2-Klein Image Detailer Best)

### How to Add a 3rd (or New) Workflow

1. **Add Workflow JSON to `workflows/`**:
   Copy or export your workflow JSON into `services/comfy-worker/workflows/my_new_workflow.json`.

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

4. **Add Option in Frontend (`frontend/event-manage.html`)**:
   ```html
   <select id="ai-workflow-select" style="width:100%;max-width:320px;">
     <option value="seedvr2_upscale">SeedVR2 4x Upscale</option>
     <option value="flux2_klein_detailer">Flux2-Klein Image Detailer Best</option>
     <option value="my_new_workflow">My New Workflow Display Name</option>
   </select>
   ```

5. **Restart Local Worker**:
   Restart `main.py` so the local worker picks up the newly registered workflow mapping:
   ```bash
   cd services/comfy-worker
   ./venv/bin/python main.py
   ```

6. **Deploy Updates Online (AWS Lambda Backend)**:
   Rebuild and deploy the cloud Lambda function image to update the live backend API Gateway and frontend UI:
   ```bash
   make update-lambda env=dev TAG=v4
   ```

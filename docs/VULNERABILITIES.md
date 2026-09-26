# SnapEvent — Security Vulnerability Audit

> **Status:** Catalogued for future remediation  
> **Date:** 2026-07-18  
> **Priority:** Address after image loading optimization

---

## Critical Vulnerabilities

### 1. CORS Wildcard with Credentials
**File:** [`main.py`](file:///home/rahul/projects/facerecog/services/api/main.py#L30-L36)  
**Issue:** `allow_origins=["*"]` combined with `allow_credentials=True` allows any website to make authenticated requests to the API, enabling cross-site request forgery (CSRF) attacks.  
**Fix:** Set `allow_origins` to specific domains (e.g., `["https://yourdomain.com"]`).

### 2. S3 CORS Wildcard
**File:** [`storage/main.tf`](file:///home/rahul/projects/facerecog/terraform/modules/storage/main.tf#L37-L46)  
**Issue:** `allowed_origins = ["*"]` on the S3 bucket CORS config. Any website can trigger uploads/downloads.  
**Fix:** Restrict to the application's domain(s).

### 3. Content-Type Injection on Presigned POST
**File:** [`storage.py`](file:///home/rahul/projects/facerecog/services/api/storage.py#L95-L97)  
**Issue:** `["starts-with", "$Content-Type", ""]` in presigned POST conditions allows any Content-Type, meaning a user could upload an HTML file or executable disguised as an image.  
**Fix:** Restrict to specific image MIME types with an explicit list in conditions.

### 4. Client-Controlled `s3_key` in Upload Confirm
**File:** [`participant.py`](file:///home/rahul/projects/facerecog/services/api/routers/participant.py#L149-L181)  
**Issue:** The `/confirm` endpoint accepts `s3_key` directly from the client body (`body.s3_key`). A malicious client could submit any arbitrary S3 key, potentially linking to another event's photos or a non-existent object. The server should derive the key from the `photo_id` instead.  
**Fix:** Server-side lookup of the expected `s3_key` from a pending-upload record keyed by `photo_id`, or regenerate the key from the photo_id.

### 5. Header Injection in Content-Disposition
**File:** [`storage.py`](file:///home/rahul/projects/facerecog/services/api/storage.py#L70-L71)  
**Issue:** `download_filename` is passed directly into the `ResponseContentDisposition` header without sanitization. Filenames containing `"` or newlines could inject HTTP headers.  
**Fix:** Sanitize the filename — strip special characters, use RFC 6266 `filename*` encoding.

---

## High Vulnerabilities

### 6. No Rate Limiting
**Files:** All routers, especially [`auth.py`](file:///home/rahul/projects/facerecog/services/api/routers/auth.py)  
**Issue:** No rate limiting on any endpoint. The `/auth/request` magic link endpoint is especially vulnerable to email bombing and abuse.  
**Fix:** Implement API Gateway throttling, WAF rules, or application-level rate limiting.

### 7. DynamoDB Scan for Access Code Validation
**File:** [`db.py`](file:///home/rahul/projects/facerecog/services/api/db.py#L328-L346)  
**Issue:** `validate_participant_code()` uses a full table `scan` to find access codes. This is O(n) on the entire table — a denial-of-service risk at scale and expensive per-invocation.  
**Fix:** Use a GSI (e.g., `GSI2PK = ACCESS#{code}`) for O(1) lookup.

### 8. Presigned URLs Too Long-Lived
**File:** [`storage.py`](file:///home/rahul/projects/facerecog/services/api/storage.py#L63-L77)  
**Issue:** Default presigned URL expiry is 3600 seconds (1 hour). For gallery browsing, this is excessive and means a leaked URL grants access for a long time.  
**Fix:** Use shorter expiry for view URLs (e.g., 5-15 minutes), longer for downloads only when explicitly requested.

### 9. No Input Validation on `event_code` Path Parameter
**File:** [`participant.py`](file:///home/rahul/projects/facerecog/services/api/routers/participant.py)  
**Issue:** The `code` path parameter in routes like `/e/{code}/photos` is not validated against the participant's resolved `event_code`. The participant auth resolves the event from the access code, but the path parameter `code` is ignored — which is confusing but not exploitable in the current flow. However, it could become a bug if routing logic changes.  
**Fix:** Validate that the path `code` matches `ac["event_code"]`.

---

## Medium Vulnerabilities

### 10. Session Tokens Not Cryptographically Strong (Unverified)
**File:** [`auth.py`](file:///home/rahul/projects/facerecog/services/api/routers/auth.py)  
**Issue:** Need to verify that session tokens use `secrets.token_urlsafe()` or equivalent CSPRNG. If using `uuid4()`, it's weaker but acceptable. If using anything else, it's a vulnerability.

### 11. No Content Security Policy (CSP) Headers
**File:** [`main.py`](file:///home/rahul/projects/facerecog/services/api/main.py)  
**Issue:** No CSP, X-Frame-Options, or other security headers. The app is vulnerable to clickjacking and XSS escalation.  
**Fix:** Add security middleware with CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy headers.

### 12. `force_destroy` on Production S3 Bucket
**File:** [`storage/main.tf`](file:///home/rahul/projects/facerecog/terraform/modules/storage/main.tf#L5)  
**Issue:** `force_destroy = var.env != "prod"` — but this means a simple variable misconfiguration could enable force_destroy in prod.  
**Fix:** Remove `force_destroy` entirely or add a safeguard.

### 13. Docs Endpoint Exposed in Dev
**File:** [`main.py`](file:///home/rahul/projects/facerecog/services/api/main.py#L27)  
**Issue:** `/docs` (Swagger UI) is enabled when `ENV=dev`. If someone deploys with the wrong env var, the full API schema is exposed.  
**Fix:** Use explicit opt-in rather than opt-out.

### 14. Path Traversal in Static File Serving
**File:** [`main.py`](file:///home/rahul/projects/facerecog/services/api/main.py#L63-L68)  
**Issue:** The `serve_page` catch-all route constructs a file path from user input: `f"{FRONTEND_DIR}/{page}.html"`. While `os.path.exists()` limits exposure, a crafted `page` value like `../../../etc/passwd` (without `.html` appended) could be probed. FastAPI/Starlette generally handles this, but it's worth hardening.  
**Fix:** Validate that the resolved path is within `FRONTEND_DIR` using `os.path.realpath()`.

### 15. XSS in Gallery via `original_name`
**File:** [`gallery.html`](file:///home/rahul/projects/facerecog/frontend/gallery.html#L143-L144)  
**Issue:** While `escHtml()` is used for the `alt` attribute, the `photo.url` is injected directly into `src` without validation. If a presigned URL were somehow manipulated, it could lead to issues. More critically, the `escHtml` function in `event-manage.html` is used inconsistently.

---

## Low / Informational

### 16. No HTTPS Enforcement
**Issue:** No redirect from HTTP to HTTPS at the application level. Relies entirely on API Gateway configuration.

### 17. DynamoDB Scan for Expired Events
**File:** [`db.py`](file:///home/rahul/projects/facerecog/services/api/db.py#L263-L274)  
**Issue:** `get_expired_events()` uses a full table scan. At scale, this becomes slow and expensive.  
**Fix:** Use a GSI with `expires_at` as sort key, or use DynamoDB TTL with Streams.

### 18. No Audit Trail for Organiser Actions
**Issue:** Only participant actions are logged. Organiser actions (create event, revoke code, etc.) have no audit trail.

### 19. Missing `HttpOnly` / `Secure` / `SameSite` Cookie Attributes
**File:** Need to verify cookie settings in `auth.py`. If session cookies lack these attributes, they're vulnerable to XSS theft and CSRF.

---

*This document will be revisited after the image loading optimization is complete.*

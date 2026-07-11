.PHONY: build push deploy destroy plan

# ── Config ───────────────────────────────────────────────────────────────────
TAG     ?= latest
ENV     ?= dev
REGION  ?= ap-south-1
ECR_URL  = $(shell cd terraform/environments/$(ENV) && terraform output -raw ecr_repository 2>/dev/null)

# ── Build Lambda Container Image ─────────────────────────────────────────────
build:
	docker build --platform linux/amd64 --provenance=false -t snapevent:$(TAG) -f Dockerfile .

# ── Push to ECR ───────────────────────────────────────────────────────────────
push: build
	aws ecr get-login-password --region $(REGION) | \
		docker login --username AWS --password-stdin $(ECR_URL)
	docker tag snapevent:$(TAG) $(ECR_URL):$(TAG)
	docker push $(ECR_URL):$(TAG)
	@echo "✅ Pushed $(ECR_URL):$(TAG)"

# ── Update Lambda function with new image ─────────────────────────────────────
update-lambda: push
	aws lambda update-function-code \
		--function-name snapevent-$(ENV)-api \
		--image-uri $(ECR_URL):$(TAG) \
		--region $(REGION)
	aws lambda update-function-code \
		--function-name snapevent-$(ENV)-cleanup \
		--image-uri $(ECR_URL):$(TAG) \
		--region $(REGION)
	@echo "✅ Updated Lambda functions with $(TAG)"

# ── Terraform: Init ──────────────────────────────────────────────────────────
init:
	cd terraform/environments/$(ENV) && terraform init

# ── Terraform: Plan ──────────────────────────────────────────────────────────
plan:
	cd terraform/environments/$(ENV) && \
		terraform plan -var="image_tag=$(TAG)"

# ── Terraform: Deploy ────────────────────────────────────────────────────────
deploy:
	cd terraform/environments/$(ENV) && \
		terraform init && \
		terraform apply -var="image_tag=$(TAG)" -auto-approve

# ── Terraform: Destroy ────────────────────────────────────────────────────────
destroy:
	@echo "⚠️  This will destroy ALL infrastructure in ENV=$(ENV). Ctrl+C to cancel."
	@sleep 5
	cd terraform/environments/$(ENV) && \
		terraform init && \
		terraform destroy -var="image_tag=$(TAG)" -auto-approve

# ── Show outputs ──────────────────────────────────────────────────────────────
outputs:
	cd terraform/environments/$(ENV) && terraform output

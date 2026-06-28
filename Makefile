.PHONY: dev dev-down build push deploy destroy logs shell

# ── Config ───────────────────────────────────────────────────────────────────
TAG     ?= latest
ENV     ?= dev
ECR_URL ?= $(shell aws ecr describe-repositories --query 'repositories[0].repositoryUri' --output text 2>/dev/null | sed 's|/snapevent-.*||')

# ── Local Dev ─────────────────────────────────────────────────────────────────
dev:
	@[ -f .env ] || (cp .env.example .env && echo "📋 Created .env from .env.example — edit it before continuing")
	docker compose up --build

dev-down:
	docker compose down -v

logs:
	docker compose logs -f control

shell:
	docker compose exec control bash

# ── Build Images ──────────────────────────────────────────────────────────────
build:
	docker build -t snapevent-control:$(TAG) -f docker/control/Dockerfile .
	docker build -t snapevent-event:$(TAG)   -f docker/event/Dockerfile   .

# ── Push to ECR ───────────────────────────────────────────────────────────────
push: build
	aws ecr get-login-password --region us-east-1 | \
		docker login --username AWS --password-stdin $(ECR_URL)
	docker tag snapevent-control:$(TAG) $(ECR_URL)/snapevent-control:$(TAG)
	docker tag snapevent-event:$(TAG)   $(ECR_URL)/snapevent-event:$(TAG)
	docker push $(ECR_URL)/snapevent-control:$(TAG)
	docker push $(ECR_URL)/snapevent-event:$(TAG)
	@echo "✅ Pushed snapevent-control:$(TAG) and snapevent-event:$(TAG)"

# ── Terraform: Deploy ─────────────────────────────────────────────────────────
deploy: push
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

# ── Terraform: Plan only ──────────────────────────────────────────────────────
plan:
	cd terraform/environments/$(ENV) && \
		terraform init && \
		terraform plan -var="image_tag=$(TAG)"

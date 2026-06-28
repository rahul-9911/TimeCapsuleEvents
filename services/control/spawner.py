"""
Control Plane — Container Spawner
Abstracts Docker SDK (dev) vs AWS ECS (staging/prod).
"""
import asyncio
import os
import time
import logging

logger = logging.getLogger(__name__)

ENV = os.getenv("ENV", "dev")


# ── Public interface ──────────────────────────────────────────────────────────

async def spawn_event(event_code: str) -> str:
    """
    Spin up an event container.
    Returns the internal URL: http://<host>:8000
    """
    if ENV == "dev":
        return await _spawn_docker(event_code)
    else:
        return await _spawn_ecs(event_code)


async def stop_event(event_code: str, task_arn: str | None = None) -> None:
    if ENV == "dev":
        await _stop_docker(event_code)
    else:
        await _stop_ecs(task_arn)


def get_event_internal_url(event_code: str) -> str:
    """
    Derive the internal URL for an event container without DB lookup.
    Consistent with how the spawner names/registers containers.
    """
    if ENV == "dev":
        return f"http://snapevent-event-{event_code}:8000"
    else:
        # ECS tasks registered with Service Connect or looked up by private IP
        # The stored internal_url in event_registry is the source of truth on AWS
        return f"http://event-{event_code}.snapevent.local:8000"


# ── Docker (dev) ──────────────────────────────────────────────────────────────

async def _spawn_docker(event_code: str) -> str:
    import docker  # type: ignore

    container_name = f"snapevent-event-{event_code}"
    network = os.getenv("DOCKER_NETWORK", "snapevent_default")
    image = os.getenv("EVENT_IMAGE", "snapevent-event:latest")
    efs_local = os.getenv("EFS_MOUNT", "/efs")

    client = docker.from_env()

    # Remove stale container with same name if exists
    try:
        old = client.containers.get(container_name)
        old.remove(force=True)
        logger.info("Removed stale container %s", container_name)
    except docker.errors.NotFound:
        pass

    container = client.containers.run(
        image=image,
        name=container_name,
        detach=True,
        network=network,
        environment={
            "EVENT_CODE": event_code,
            "S3_ENDPOINT": os.getenv("S3_ENDPOINT", "http://minio:9000"),
            "S3_BUCKET": os.getenv("S3_BUCKET", "snapevent-dev"),
            "S3_REGION": os.getenv("S3_REGION", "us-east-1"),
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            "EFS_MOUNT": "/data",
        },
        volumes={
            # Share the EFS volume — event subdir is isolated inside the app
            efs_local: {"bind": "/data", "mode": "rw"},
        },
        labels={
            "traefik.enable": "true",
            f"traefik.http.routers.event-{event_code}.rule": f"PathPrefix(`/e/{event_code}`)",
            f"traefik.http.routers.event-{event_code}.priority": "10",
            f"traefik.http.services.event-{event_code}.loadbalancer.server.port": "8000",
        },
    )

    # Wait until the container's health check passes (max 30s)
    internal_url = f"http://{container_name}:8000"
    await _wait_for_health(internal_url, timeout=30)
    logger.info("Event container %s is healthy at %s", container_name, internal_url)
    return internal_url


async def _stop_docker(event_code: str) -> None:
    import docker  # type: ignore

    container_name = f"snapevent-event-{event_code}"
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
        container.stop(timeout=5)
        container.remove()
        logger.info("Stopped and removed %s", container_name)
    except docker.errors.NotFound:
        logger.warning("Container %s not found — already stopped?", container_name)


# ── ECS Fargate (staging / prod) ──────────────────────────────────────────────

async def _spawn_ecs(event_code: str) -> str:
    import boto3  # type: ignore

    ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))
    cluster = os.getenv("ECS_CLUSTER")
    task_def = os.getenv("EVENT_TASK_DEFINITION")
    subnets = os.getenv("ECS_SUBNETS", "").split(",")
    sg = os.getenv("EVENT_SECURITY_GROUP")

    response = ecs.run_task(
        cluster=cluster,
        taskDefinition=task_def,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": [sg],
                "assignPublicIp": "DISABLED",
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": "event",
                    "environment": [{"name": "EVENT_CODE", "value": event_code}],
                }
            ]
        },
        capacityProviderStrategy=[
            {"capacityProvider": "FARGATE_SPOT", "weight": 1},
            {"capacityProvider": "FARGATE", "weight": 0, "base": 1},
        ],
    )

    task_arn = response["tasks"][0]["taskArn"]
    logger.info("Started ECS task %s for event %s", task_arn, event_code)

    # Wait for task to reach RUNNING and get private IP
    private_ip = await _wait_for_ecs_task(ecs, cluster, task_arn, timeout=90)
    internal_url = f"http://{private_ip}:8000"
    logger.info("ECS task running at %s", internal_url)
    return internal_url


async def _stop_ecs(task_arn: str) -> None:
    import boto3  # type: ignore

    ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ecs.stop_task(cluster=os.getenv("ECS_CLUSTER"), task=task_arn, reason="Event expired")
    logger.info("Stopped ECS task %s", task_arn)


async def _wait_for_ecs_task(ecs_client, cluster: str, task_arn: str, timeout: int = 90) -> str:
    """Poll until task is RUNNING and return its private IP."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = ecs_client.describe_tasks(cluster=cluster, tasks=[task_arn])
        task = resp["tasks"][0]
        status = task.get("lastStatus", "")
        if status == "RUNNING":
            for attachment in task.get("attachments", []):
                for detail in attachment.get("details", []):
                    if detail["name"] == "privateIPv4Address":
                        return detail["value"]
        if status in ("STOPPED", "DEPROVISIONING"):
            raise RuntimeError(f"ECS task {task_arn} stopped unexpectedly: {task.get('stoppedReason')}")
        await asyncio.sleep(3)
    raise TimeoutError(f"ECS task {task_arn} did not reach RUNNING within {timeout}s")


# ── Shared health check ───────────────────────────────────────────────────────

async def _wait_for_health(url: str, timeout: int = 30) -> None:
    import httpx  # type: ignore

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{url}/health", timeout=3.0)
                if r.status_code == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(1)
    raise TimeoutError(f"Service at {url} did not become healthy within {timeout}s")

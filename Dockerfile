FROM public.ecr.aws/lambda/python:3.12

# Install dependencies
COPY services/api/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application code
COPY services/api/ ${LAMBDA_TASK_ROOT}/

# Copy frontend files
COPY frontend/ /frontend/

# Default handler (main API — overridden for cleanup Lambda via Terraform image_config)
CMD ["main.handler"]

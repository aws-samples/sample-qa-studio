# Nova Act Worker - Docker Setup

This directory contains the Docker setup for running the Nova Act worker in a containerized environment.

## Prerequisites

- Docker and Docker Compose installed
- AWS credentials configured
- Access to the DynamoDB table and S3 bucket

## Quick Start

### 1. Environment Setup

Copy the environment template and fill in your values:

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 2. Build and Run (Single Execution)

```bash
# Build the Docker image
docker-compose build

# Run a single execution
docker-compose up nova-worker
```

### 3. Run with SQS Queue Processing

```bash
# Set SQS_QUEUE_URL in your .env file, then:
docker-compose --profile sqs up nova-worker-sqs
```

## Manual Docker Commands

### Build Image

```bash
docker build -t nova-act-worker .
```

### Run Single Execution

```bash
docker run --rm \
  -e USECASE_ID=your-usecase-id \
  -e EXECUTION_ID=your-execution-id \
  -e DYNAMODB_TABLE_NAME=accept-ai \
  -e AWS_REGION=us-east-1 \
  -e S3_BUCKET=your-bucket \
  -e AWS_ACCESS_KEY_ID=your-key \
  -e AWS_SECRET_ACCESS_KEY=your-secret \
  -v $(pwd)/logs:/app/logs \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  --shm-size=2g \
  nova-act-worker
```

### Run SQS Worker

```bash
docker run --rm \
  -e SQS_QUEUE_URL=your-queue-url \
  -e DYNAMODB_TABLE_NAME=accept-ai \
  -e AWS_REGION=us-east-1 \
  -e S3_BUCKET=your-bucket \
  -e AWS_ACCESS_KEY_ID=your-key \
  -e AWS_SECRET_ACCESS_KEY=your-secret \
  -v $(pwd)/logs:/app/logs \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  --shm-size=2g \
  nova-act-worker python run_worker.py
```

## Environment Variables

### Required
- `USECASE_ID`: The usecase identifier
- `EXECUTION_ID`: The execution identifier  
- `DYNAMODB_TABLE_NAME`: DynamoDB table name (default: accept-ai)
- `AWS_REGION`: AWS region (default: us-east-1)
- `S3_BUCKET`: S3 bucket for artifacts

### AWS Authentication
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `AWS_SESSION_TOKEN`: AWS session token (for temporary credentials)

### Optional
- `SQS_QUEUE_URL`: SQS queue URL for queue-based processing
- `LOGS_DIRECTORY`: Directory for logs (default: /app/logs)

## Docker Configuration

### Security Settings
The container requires specific security settings for Chrome/Chromium:
- `--cap-add=SYS_ADMIN`: Required for Chrome sandbox
- `--security-opt seccomp=unconfined`: Disables seccomp for Chrome
- `--shm-size=2g`: Increases shared memory for Chrome

### Resource Limits
Recommended resource limits:
- Memory: 4GB limit, 2GB reservation
- CPU: 2 cores limit, 1 core reservation

### Volumes
- `./logs:/app/logs`: Persist execution logs
- `~/.aws:/home/worker/.aws:ro`: Mount AWS credentials (read-only)

## Troubleshooting

### Chrome/Chromium Issues
If you encounter Chrome-related errors:
1. Ensure `--cap-add=SYS_ADMIN` is set
2. Increase `--shm-size` if needed
3. Check that `DISPLAY=:99` is set

### AWS Permissions
Ensure your AWS credentials have permissions for:
- DynamoDB: Read/Write access to the table
- S3: Read/Write access to the bucket
- SQS: Receive/Delete messages (if using SQS mode)

### Memory Issues
If the container runs out of memory:
1. Increase Docker memory limits
2. Monitor Chrome processes

## Logs

Execution logs are stored in the `./logs` directory and are organized by execution ID:
```
logs/
├── execution-123/
│   ├── video.mp4
│   ├── screenshots/
│   └── logs/
```

## Development

For development, you can mount the source code:

```bash
docker run --rm \
  -v $(pwd):/app \
  -e USECASE_ID=test \
  -e EXECUTION_ID=test \
  # ... other env vars
  nova-act-worker
```
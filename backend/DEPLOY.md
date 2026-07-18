# Deploying NexusChain Autopilot to Alibaba Cloud

Runbook for the actual deployment once an Alibaba Cloud account + credentials exist.
Everything below has been dry-run locally (Docker image builds and boots; the app has
been verified end-to-end against a real Postgres instance over `psycopg`) but not yet
executed against a real Alibaba Cloud account.

## 1. Provision an RDS (PostgreSQL) or PolarDB instance

1. Create a PostgreSQL RDS or PolarDB instance in the Alibaba Cloud console.
2. Create a database (e.g. `nexuschain_autopilot`) and a user with access to it.
3. Add the ECS instance's (or Function Compute's) security group / VPC to the RDS
   whitelist so the app can reach it.
4. Build the connection string using the **psycopg3** driver prefix (not bare
   `postgresql://` — SQLAlchemy defaults to psycopg2, which isn't installed):
   ```
   DATABASE_URL=postgresql+psycopg://<user>:<password>@<rds-host>:5432/nexuschain_autopilot
   ```

## 2. Create an OSS bucket

1. Create a bucket (e.g. `nexuschain-autopilot-payloads`) in the Alibaba Cloud OSS console, in
   the same region as the ECS instance for lower latency.
2. Create a RAM user (or use a RAM role attached to the ECS instance) with
   `AliyunOSSFullAccess` scoped to just that bucket, and grab its AccessKey ID/secret.
3. Set:
   ```
   OSS_ACCESS_KEY_ID=...
   OSS_ACCESS_KEY_SECRET=...
   OSS_ENDPOINT=https://oss-<region>.aliyuncs.com
   OSS_BUCKET_NAME=nexuschain-autopilot-payloads
   ```
   This is the Alibaba Cloud API integration referenced in the submission's "Proof of
   Alibaba Cloud Deployment" requirement — see `app/oss_client.py` for the code that
   calls it (`bucket.put_object(...)`).

## 3. Build and push the container image

```bash
cd backend
docker build -t nexuschain-autopilot:latest .

# Push to Alibaba Cloud Container Registry (ACR)
docker tag nexuschain-autopilot:latest registry.<region>.aliyuncs.com/<namespace>/nexuschain-autopilot:latest
docker login registry.<region>.aliyuncs.com
docker push registry.<region>.aliyuncs.com/<namespace>/nexuschain-autopilot:latest
```

## 4. Run it on ECS

1. Launch (or reuse) an ECS instance with Docker installed.
2. Pull and run the image, passing all required env vars:
   ```bash
   docker run -d --name nexuschain-autopilot -p 80:8000 \
     -e DASHSCOPE_API_KEY=... \
     -e DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1 \
     -e QWEN_MODEL=qwen-plus \
     -e DATABASE_URL=postgresql+psycopg://... \
     -e SLACK_WEBHOOK_URL=... \
     -e OSS_ACCESS_KEY_ID=... \
     -e OSS_ACCESS_KEY_SECRET=... \
     -e OSS_ENDPOINT=... \
     -e OSS_BUCKET_NAME=... \
     registry.<region>.aliyuncs.com/<namespace>/nexuschain-autopilot:latest
   ```
3. Open the ECS security group's port 80 (or whatever's mapped) to the internet, or put
   it behind an SLB (Server Load Balancer) for a stable public endpoint.
4. Confirm with `curl http://<ecs-public-ip>/health` → `{"status": "ok"}`.

(Function Compute is a viable alternative to ECS if a fully-managed/serverless target is
preferred — it takes the same container image via its custom-container runtime; the app
itself needs no changes either way.)

## 5. Proof-of-deployment artifact for submission

- Record a short screen capture showing: `curl http://<ecs-public-ip>/health` returning
  `{"status": "ok"}` from a terminal, then opening `http://<ecs-public-ip>/dashboard` in
  a browser — both hitting the live Alibaba Cloud IP, not localhost.
- Link `backend/app/oss_client.py` in the submission as the code file demonstrating
  Alibaba Cloud API usage (OSS `put_object`).

## Local dry-run (already verified, no cloud account needed)

```bash
docker build -t nexuschain-autopilot:test .
docker run -d --name nexuschain-autopilot-test -p 18000:8000 \
  -e DASHSCOPE_API_KEY=dummy \
  -e DATABASE_URL=sqlite:////tmp/nexuschain_autopilot.db \
  nexuschain-autopilot:test
curl localhost:18000/health   # -> {"status":"ok"}
curl localhost:18000/dashboard
docker stop nexuschain-autopilot-test && docker rm nexuschain-autopilot-test
```

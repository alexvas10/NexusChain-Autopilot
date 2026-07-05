import os

from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ops_autopilot.db")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# Alibaba Cloud OSS — raw request payloads (would be inbound emails/PDFs in production)
# are archived here for audit purposes. Left blank in local dev; falls back to writing
# under ./local_oss_store/ instead of hitting the real API.
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME", "")

# Above this estimated cost delta (USD), a disruption reroute always needs human approval
# regardless of what the Qwen classifier decides — a belt-and-braces financial guardrail.
DISRUPTION_COST_APPROVAL_THRESHOLD = float(os.getenv("DISRUPTION_COST_APPROVAL_THRESHOLD", "200"))

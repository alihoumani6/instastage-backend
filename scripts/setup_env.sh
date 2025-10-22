#!/usr/bin/env bash
set -euo pipefail

# Move to repo root (script may be run from anywhere)
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

python - <<'PY'
import os
from dotenv import load_dotenv
load_dotenv()
print("USE_S3:", os.getenv("USE_S3"))
print("AWS_DEFAULT_REGION:", os.getenv("AWS_DEFAULT_REGION"))
print("S3_BUCKET:", os.getenv("S3_BUCKET"))
print("S3_PREFIX:", os.getenv("S3_PREFIX"))
print("S3_URL_EXPIRES:", os.getenv("S3_URL_EXPIRES"))
print("OPENAI_API_KEY set?", bool(os.getenv("OPENAI_API_KEY")))
PY

echo "✅ Environment ready. Start the server with:"
echo "source .venv/bin/activate && uvicorn main:app --reload"

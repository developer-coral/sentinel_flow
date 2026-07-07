#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://localhost:8000/health >/dev/null
curl -fsS -X POST http://localhost:8000/analyze \
  -F "text=$(cat samples/high-risk-contract.txt)" | python -m json.tool

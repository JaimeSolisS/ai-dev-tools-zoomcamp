#!/bin/bash
# Wait until <url>/health reports a healthy app and database running <version>.
#   healthcheck.sh <url> <version>
set -euo pipefail
URL=$1
VERSION=$2

echo "==> Waiting for $URL/health to report version $VERSION"
for _ in $(seq 1 60); do
  body=$(curl -s -m 5 "$URL/health" || true)
  if python3 -c '
import json, sys
h = json.loads(sys.argv[1])
sys.exit(0 if h["status"] == "ok" and h["database"] == "ok" and h["version"] == sys.argv[2] else 1)
' "$body" "$VERSION" 2>/dev/null; then
    echo "Healthy: $body"
    exit 0
  fi
  sleep 5
done
echo "Not healthy after 5 minutes; last response: ${body:-<none>}" >&2
exit 1

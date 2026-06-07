#!/bin/sh
# POST one of the API's cron endpoints, log response, exit non-zero on
# any non-2xx so Railway's cron history goes red instead of green.
#
# All knobs come from env vars set in the Railway service:
#   CRON_BASE_URL       (required) — https://api-production-d64e.up.railway.app
#   CRON_PATH           (required) — /admin/cron/daily-tip
#   CRON_SHARED_SECRET  (required) — value of CRON_SHARED_SECRET on the API service
#   CRON_TIMEOUT_SECONDS (optional, default 300) — max seconds before we give up
set -eu

require() {
  if [ -z "${2:-}" ]; then
    echo "[cron] FATAL: env var $1 is not set" >&2
    exit 2
  fi
}

require CRON_BASE_URL "${CRON_BASE_URL:-}"
require CRON_PATH "${CRON_PATH:-}"
require CRON_SHARED_SECRET "${CRON_SHARED_SECRET:-}"

TIMEOUT="${CRON_TIMEOUT_SECONDS:-300}"
URL="${CRON_BASE_URL}${CRON_PATH}"
RESPONSE_FILE="$(mktemp)"

echo "[cron] $(date -u +'%Y-%m-%dT%H:%M:%SZ') POST ${URL}"
echo "[cron] timeout=${TIMEOUT}s"

# -sS  silent body but show curl errors
# -L   follow redirects
# -X POST
# -f is NOT used — we want to read the body even on 4xx/5xx for debugging
http_code=$(
  curl -sS -L -X POST \
    --max-time "${TIMEOUT}" \
    -o "${RESPONSE_FILE}" \
    -w '%{http_code}' \
    -H "X-Cron-Secret: ${CRON_SHARED_SECRET}" \
    -H "Content-Type: application/json" \
    "${URL}"
)

echo "[cron] HTTP ${http_code}"
echo "[cron] --- response body ---"
cat "${RESPONSE_FILE}"
echo
echo "[cron] --- end response ---"
rm -f "${RESPONSE_FILE}"

# Treat 2xx as success, everything else as failure (including 0 from a
# curl-level error — connection refused, DNS, timeout).
case "${http_code}" in
  2*) echo "[cron] OK"; exit 0 ;;
  *)  echo "[cron] FAILED (status=${http_code})" >&2; exit 1 ;;
esac

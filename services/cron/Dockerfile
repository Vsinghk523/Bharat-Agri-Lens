# Minimal Railway cron runner.
#
# One image, four Railway services. Each service points at this same
# Dockerfile via its source-directory setting and overrides three env
# vars + the cron schedule in the Railway dashboard:
#
#   CRON_BASE_URL       — e.g. https://api-production-d64e.up.railway.app
#   CRON_PATH           — e.g. /admin/cron/daily-tip
#   CRON_SHARED_SECRET  — same value as the API service's env var
#
# The container POSTs the URL, logs the response, and exits 0 on 2xx /
# exit 1 on anything else (so Railway's cron history shows red on
# failure instead of silently swallowing 500s).
#
# Why not curlimages/curl directly?  It runs as a non-root user, which
# trips up some Railway build paths, and we want our own entrypoint
# wrapping curl with proper status handling.

FROM alpine:3.20

RUN apk add --no-cache curl ca-certificates \
    && rm -rf /var/cache/apk/*

COPY run.sh /usr/local/bin/run.sh
RUN chmod +x /usr/local/bin/run.sh

# Sensible default; the actual schedule comes from Railway service settings.
ENV CRON_TIMEOUT_SECONDS=300

ENTRYPOINT ["/usr/local/bin/run.sh"]

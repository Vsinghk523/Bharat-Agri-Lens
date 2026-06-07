# Railway cron runner

Tiny Alpine + curl image that POSTs a single URL with the
`X-Cron-Secret` header and exits with the right status code so
Railway's cron history accurately reflects success/failure.

The image is generic — **one Dockerfile, four Railway services.**
Each service points at this same source directory and overrides
three env vars + the cron schedule.

---

## Architecture

```
                   ┌────────────────────────────────────────────┐
                   │ Railway project                            │
                   │                                            │
                   │  ┌─────────┐                               │
                   │  │  api    │── handles HTTP + the cron     │
                   │  └─────────┘    endpoints themselves       │
                   │                                            │
                   │  ┌──────────────────────┐                  │
                   │  │  cron-daily-tip      │── 06:00 IST      │
                   │  ├──────────────────────┤                  │
                   │  │  cron-reminders      │── hourly         │
                   │  ├──────────────────────┤                  │
                   │  │  cron-outbreak       │── 06:30 IST      │
                   │  ├──────────────────────┤                  │
                   │  │  cron-train-export   │── 02:00 IST      │
                   │  └──────────────────────┘                  │
                   │           │                                │
                   │           │  POST /admin/cron/...          │
                   │           │  X-Cron-Secret: ...            │
                   │           ▼                                │
                   │  ┌─────────┐                               │
                   │  │  api    │  → 200 + counters             │
                   │  └─────────┘                               │
                   └────────────────────────────────────────────┘
```

All four cron services build from this same `services/cron/`
directory. They differ only in env vars and cron schedule.

---

## One-time setup per cron service

For each of the four jobs in the table below:

1. **Railway → New Service → GitHub Repo**
   Pick the `bharat-agri-lens` repo.

2. **Settings → Source → Root Directory**
   Set to `services/cron`.

3. **Settings → Deploy → Cron Schedule**
   Paste the cron expression from the table (Railway uses UTC).

4. **Variables**
   Add:
   - `CRON_BASE_URL` = `https://api-production-d64e.up.railway.app`
   - `CRON_PATH` = the path from the table
   - `CRON_SHARED_SECRET` = use Railway's **reference variable** picker
     to bind to the `api` service's `CRON_SHARED_SECRET` (DO NOT
     paste the value — references stay in sync if you ever rotate
     the secret).

5. **Settings → Service Name**
   Use the service name from the table so logs/billing are
   readable.

6. **Deploy**.
   Watch the build, then trigger a manual run from the Deployments
   tab and confirm the log shows `[cron] OK` and a 2xx counter
   response.

---

## The four services

| Service name | Cron (UTC) | India local | `CRON_PATH` | What runs |
|---|---|---|---|---|
| `cron-reminders` | `0 * * * *` | every hour on the hour | `/admin/cron/process-treatment-reminders` | Fires due `treatment_reminders` rows; flips status `pending → sent`. Re-reads user preference at fire time so a fresh Settings flip wins. |
| `cron-daily-tip` | `30 0 * * *` | 06:00 IST | `/admin/cron/daily-tip` | Sends one rotating tip push to every user with `notif_daily_tips=true`. |
| `cron-outbreak` | `0 1 * * *` | 06:30 IST | `/admin/cron/process-outbreak-alerts` | Detects ≥5 same-infection diagnoses in same pincode in last 7 days; pushes to non-reporter users in that pincode; idempotent within an ISO week. |
| `cron-train-export` | `30 20 * * *` | 02:00 IST | `/admin/cron/export-training-data` | Builds HF Datasets bundle of every reviewed diagnostic since last watermark; pushes to HF Hub. |

The 06:00 / 06:30 IST stagger for `daily-tip` and `outbreak` is
intentional — back-to-back pushes 30 min apart is two impressions
in a row without bunching them in the same minute.

---

## Why each schedule

- **`process-treatment-reminders` — hourly.** Reminders are
  scheduled at specific times (e.g. "Day 3, 09:00 IST"). The cron
  just fires whatever's due. Hourly cadence means worst-case
  latency is 59 min, which is fine for a 7-day treatment loop.

- **`daily-tip` — 06:00 IST.** Indian farmers' phone-engagement
  peak is dawn through breakfast. 06:00 catches them before
  fieldwork starts.

- **`process-outbreak-alerts` — 06:30 IST.** Same peak as daily
  tip, offset 30 min so the user doesn't see two pushes within
  seconds of each other. Outbreak alerts use weekly dedup, so the
  exact daily slot doesn't matter — only that it runs once.

- **`export-training-data` — 02:00 IST.** Pure off-peak. The
  export reads from prod DB and writes to HF Hub; doing it when no
  one's diagnosing keeps the DB hot path uncontended.

---

## Verifying a service works

After Railway deploys it, hit **Deployments → ⋯ → Run Deployment**
to trigger an out-of-schedule execution. Then check the logs.

A healthy run looks like:

```
[cron] 2026-06-07T01:00:01Z POST https://api-production-d64e.up.railway.app/admin/cron/daily-tip
[cron] timeout=300s
[cron] HTTP 200
[cron] --- response body ---
{"users_targeted":0,"pushes_sent":0,"skipped_pref":0,"skipped_no_fcm":0,"already_sent_today":0}
[cron] --- end response ---
[cron] OK
```

Anything other than `HTTP 2xx` exits the container with status 1
and shows red in the Railway deployments list.

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `HTTP 401, Invalid or missing cron secret` | `CRON_SHARED_SECRET` mismatch with API service | Re-link the reference variable; redeploy |
| `[cron] FAILED (status=000)` | Connection / DNS / timeout | Check `CRON_BASE_URL` is correct and API is up |
| Cron triggers but nothing happens | Schedule is in IST but Railway uses UTC | Convert IST → UTC (subtract 5h30) |
| Multiple runs in same minute | Two services have the same schedule | Railway docs note this — stagger by ≥1 minute |

---

## Manual ad-hoc test from anywhere

Same payload the runner sends, but from your shell:

```bash
curl -sS -X POST \
  -H "X-Cron-Secret: $CRON_SHARED_SECRET" \
  https://api-production-d64e.up.railway.app/admin/cron/daily-tip
```

If that works but the Railway cron service doesn't, the bug is in
the cron-runner config, not the API.

---

## Rotating the cron secret

1. Generate a new value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. On the `api` service, update `CRON_SHARED_SECRET`. Redeploy.
3. The four cron services use reference variables, so they pick up
   the new value automatically on their next run. No code change.

---

## Local smoke-test (without Railway)

The image is self-contained; you can run it locally:

```bash
cd services/cron
docker build -t bal-cron .
docker run --rm \
  -e CRON_BASE_URL=https://api-production-d64e.up.railway.app \
  -e CRON_PATH=/admin/cron/daily-tip \
  -e CRON_SHARED_SECRET="$CRON_SHARED_SECRET" \
  bal-cron
```

Should print the same `[cron] OK` log line.

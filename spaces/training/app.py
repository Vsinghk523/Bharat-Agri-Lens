"""HF Space entrypoint: orchestrate the PlantViT training pipeline.

Flow:
    1. Download the merged ImageFolder dataset from HF Hub
       (HF_DATASET_REPO env var).
    2. Run ``bal-train`` against ``configs/plantvillage_v0.yaml``.
    3. Run ``bal-export`` on the best checkpoint to produce ONNX + labels +
       provenance.
    4. Upload the export artifacts to HF Hub (HF_MODEL_REPO env var).
    5. Auto-pause the Space so billing stops.

A small Gradio UI tails the live training log so the operator can see
progress without scraping the Space's Logs tab.

Required env / secrets (set via Space → Settings → Variables and secrets):
    HF_TOKEN        — Write token for the dataset + model repos
    HF_DATASET_REPO — e.g. "viveksk523/bal-plantvit-data"
    HF_MODEL_REPO   — e.g. "viveksk523/bal-plantvit-v0"

Optional:
    EPOCHS          — override the config's epoch count for quick smoke
                      tests (e.g. set to 2 first to verify the wiring).
    TRAINING_CONFIG — path to a different yaml under
                      repo/services/training/configs/. Defaults to
                      plantvillage_v0.yaml.
"""

from __future__ import annotations

import datetime as dt
import html
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional

from huggingface_hub import HfApi, snapshot_download

# --- Configuration --------------------------------------------------------

REPO_ROOT = Path("/home/user/repo")
TRAINING_ROOT = REPO_ROOT / "services" / "training"
CONFIG_NAME = os.environ.get("TRAINING_CONFIG", "configs/plantvillage_v0.yaml")
CONFIG_PATH = TRAINING_ROOT / CONFIG_NAME

DATA_DIR = TRAINING_ROOT / "data" / "combined"  # matches train_dir/val_dir in the config
RUN_DIR = TRAINING_ROOT / "runs" / "plantvit-v0"
EXPORT_DIR = RUN_DIR / "export"
LOG_PATH = Path("/tmp/training.log")

HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_DATASET_REPO = os.environ.get("HF_DATASET_REPO", "")
HF_MODEL_REPO = os.environ.get("HF_MODEL_REPO", "")
SPACE_ID = os.environ.get("SPACE_ID", "")  # set automatically by HF Spaces
EPOCHS_OVERRIDE = os.environ.get("EPOCHS", "").strip()

# --- Log streaming --------------------------------------------------------

# We append progress to LOG_PATH from multiple stages; the Gradio UI
# polls the file every few seconds and renders the tail.

_log_lock = threading.Lock()


def log(line: str) -> None:
    """Append a timestamped line to the training log and stdout."""
    ts = dt.datetime.utcnow().strftime("%H:%M:%S")
    formatted = f"[{ts}] {line}"
    print(formatted, flush=True)
    with _log_lock:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(formatted + "\n")


def stream_subprocess(cmd: list[str], cwd: Optional[Path] = None) -> int:
    """Run a subprocess and stream its stdout+stderr into LOG_PATH live.

    Avoids buffering surprises: each line the child prints lands in the
    log as soon as it's flushed, so the Gradio UI sees real-time training
    output (loss, val accuracy, epoch markers).
    """
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for raw in iter(proc.stdout.readline, ""):
        line = raw.rstrip()
        if not line:
            continue
        print(line, flush=True)
        with _log_lock:
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    proc.wait()
    return proc.returncode


# --- Pipeline stages ------------------------------------------------------


def stage_download_dataset() -> None:
    """Stage 1 — pull the PlantVillage ImageFolder split from HF Hub."""
    log(f"[1/5] Downloading dataset from {HF_DATASET_REPO}")
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)

    # snapshot_download grabs every file under the dataset repo; we point
    # `local_dir` directly at the path the training config expects.
    snapshot_download(
        repo_id=HF_DATASET_REPO,
        repo_type="dataset",
        local_dir=str(DATA_DIR),
        token=HF_TOKEN or None,
        allow_patterns=["train/**", "val/**"],
        max_workers=8,
    )

    train_n = sum(1 for _ in (DATA_DIR / "train").rglob("*") if _.is_file())
    val_n = sum(1 for _ in (DATA_DIR / "val").rglob("*") if _.is_file())
    log(f"    downloaded train={train_n} val={val_n}")


def stage_train() -> Path:
    """Stage 2 — run bal-train. Returns the path to best.pt."""
    log(f"[2/5] Training (config={CONFIG_NAME})")
    args = [
        "bal-train",
        "--config", str(CONFIG_PATH),
        "--run-dir", str(RUN_DIR),
    ]
    if EPOCHS_OVERRIDE:
        log(f"    EPOCHS override: {EPOCHS_OVERRIDE}")
        args += ["--epochs", EPOCHS_OVERRIDE]

    rc = stream_subprocess(args, cwd=TRAINING_ROOT)
    if rc != 0:
        raise RuntimeError(f"bal-train exited with code {rc}")
    ckpt = RUN_DIR / "best.pt"
    if not ckpt.exists():
        raise RuntimeError(f"Expected best checkpoint at {ckpt}, not found")
    log(f"    best checkpoint: {ckpt}")
    return ckpt


def stage_export(ckpt: Path) -> Path:
    """Stage 3 — bal-export to ONNX (fp32 + dynamic-int8 quantized)."""
    log("[3/5] Exporting to ONNX")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "bal-export",
        "--config", str(CONFIG_PATH),
        "--checkpoint", str(ckpt),
        "--out", str(EXPORT_DIR),
    ]
    rc = stream_subprocess(args, cwd=TRAINING_ROOT)
    if rc != 0:
        raise RuntimeError(f"bal-export exited with code {rc}")
    log(f"    exported to {EXPORT_DIR}")
    return EXPORT_DIR


def stage_upload(export_dir: Path) -> None:
    """Stage 4 — push the export bundle to the model repo on HF Hub."""
    log(f"[4/5] Uploading model artifacts to {HF_MODEL_REPO}")
    api = HfApi(token=HF_TOKEN or None)
    api.upload_folder(
        folder_path=str(export_dir),
        repo_id=HF_MODEL_REPO,
        repo_type="model",
        commit_message=f"PlantViT v0 — {dt.datetime.utcnow().isoformat()}Z",
    )
    log(f"    uploaded. https://huggingface.co/{HF_MODEL_REPO}")


def stage_pause_space() -> None:
    """Stage 5 — pause the Space so billing stops.

    Best-effort: we wrap in try/except because the call to pause itself
    is the last thing this process does. If the call fails we still
    consider the training successful; operator just has to pause manually
    via the Space's UI.
    """
    log("[5/5] Pausing Space to stop billing")
    if not SPACE_ID:
        log("    SPACE_ID not set; skipping auto-pause. Pause manually via Space settings.")
        return
    try:
        api = HfApi(token=HF_TOKEN or None)
        api.pause_space(SPACE_ID)
        log("    paused. ✅")
    except Exception as exc:  # noqa: BLE001
        log(f"    auto-pause failed ({exc!r}). Pause manually via Space settings.")


# --- Orchestration --------------------------------------------------------


def validate_environment() -> Optional[str]:
    """Return an error string if anything required is missing, else None."""
    missing: list[str] = []
    if not HF_TOKEN:
        missing.append("HF_TOKEN")
    if not HF_DATASET_REPO:
        missing.append("HF_DATASET_REPO")
    if not HF_MODEL_REPO:
        missing.append("HF_MODEL_REPO")
    if missing:
        return (
            "Missing required secrets: " + ", ".join(missing) +
            ". Set them in Space → Settings → Variables and secrets, then restart."
        )
    if not CONFIG_PATH.exists():
        return f"Training config not found: {CONFIG_PATH}"
    return None


def run_pipeline() -> None:
    LOG_PATH.write_text("")  # truncate prior run's log
    err = validate_environment()
    if err:
        log(f"[fatal] {err}")
        return
    log(f"BAL PlantViT training starting on {SPACE_ID or '(unknown space)'}")
    log(f"dataset={HF_DATASET_REPO} model={HF_MODEL_REPO} config={CONFIG_NAME}")
    try:
        stage_download_dataset()
        ckpt = stage_train()
        export_dir = stage_export(ckpt)
        stage_upload(export_dir)
        log("✅ Training pipeline complete.")
    except Exception as exc:  # noqa: BLE001
        log(f"[fatal] pipeline failed: {exc!r}")
        log(traceback.format_exc())
        return
    finally:
        # Pause even on failure — leaving a failed Space "running" on
        # A100 burns money. Operator can investigate via Logs tab after.
        stage_pause_space()


# --- Status web UI --------------------------------------------------------
#
# We deliberately avoid Gradio / Streamlit / FastAPI here because every
# extra dependency layer has been a source of import-time crashes on the
# Spaces runtime (pydantic vs gradio vs torch wheel matrix). stdlib
# ``http.server`` does the one thing we actually need: serve the live
# training log on port 7860 with a meta-refresh so the operator sees
# updates without manually reloading.

LOG_PATH.touch()  # ensure file exists before the first request


def _read_log_tail(max_lines: int = 500) -> str:
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return "(log not yet created)"
    return "".join(lines[-max_lines:])


def _status_html() -> str:
    body = html.escape(_read_log_tail())
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>BAL PlantViT Training</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    body {{ margin: 0; padding: 24px; background: #f7faf7; color: #1b2d1b; }}
    h1 {{ margin: 0 0 4px 0; color: #2d5a2d; }}
    .meta {{ color: #5a6b5a; font-size: 14px; margin-bottom: 16px; }}
    pre {{
      background: #ffffff;
      border: 1px solid #d6e2d6;
      border-radius: 8px;
      padding: 16px;
      overflow: auto;
      max-height: 75vh;
      font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
      font-size: 12.5px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #0f1a0f; color: #d6e2d6; }}
      h1 {{ color: #7fc97f; }}
      .meta {{ color: #8aa68a; }}
      pre {{ background: #1a2a1a; border-color: #2c3f2c; }}
    }}
  </style>
</head>
<body>
  <h1>🌱 BharatAgriLens · PlantViT Trainer</h1>
  <p class="meta">
    Refreshes every 5 seconds. Training runs automatically on Space start.
    When you see <code>✅ Training pipeline complete</code> and
    <code>paused. ✅</code> the Space auto-pauses to stop billing.
  </p>
  <pre>{body}</pre>
</body>
</html>
"""


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        payload = _status_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    # Quiet the default per-request stderr logging — every meta-refresh
    # tick would otherwise spam Space logs with 200 GET lines.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _serve_status() -> None:
    # ThreadingTCPServer so a slow read doesn't block the next refresh.
    with socketserver.ThreadingTCPServer(("0.0.0.0", 7860), _StatusHandler) as httpd:
        httpd.allow_reuse_address = True
        httpd.serve_forever()


# --- Boot ----------------------------------------------------------------

# 1. Background thread: run the actual training pipeline.
_train_thread = threading.Thread(
    target=run_pipeline, daemon=True, name="train-pipeline"
)
_train_thread.start()

# 2. Main thread: serve the status page on the port HF Spaces expects.
#    Blocking call — keeps the container alive until the runtime kills it
#    (or the auto-pause inside run_pipeline triggers).
if __name__ == "__main__":
    _serve_status()

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
import os
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional

import gradio as gr
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


# --- Gradio UI ------------------------------------------------------------

LOG_PATH.touch()  # ensure file exists before the first poll


def read_log_tail() -> str:
    """Return the last N lines of the training log for the UI."""
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return "(log not yet created)"
    return "".join(lines[-200:])


with gr.Blocks(title="BAL PlantViT Training") as demo:
    gr.Markdown(
        """
        # 🌱 BharatAgriLens · PlantViT Trainer

        Training runs automatically when this Space starts. Logs refresh
        every 5 seconds. When you see `✅ Training pipeline complete`
        the Space will auto-pause to stop billing.

        - Hardware required: **A100-large** (set via Space → Settings → Hardware)
        - Expected runtime: **3-4 hours** on A100, ~12-15 hours on T4
        - Cost on A100: **~$8-10** total
        """
    )
    output = gr.Textbox(
        label="Live training log",
        lines=30,
        max_lines=200,
        autoscroll=True,
    )
    # Refresh tail every 5 seconds. ``every=`` on demo.load is the
    # widely-supported pattern across Gradio 4.x and 5.x (gr.Timer
    # only exists in 5.x and Textbox.show_copy_button needs a recent
    # release — keep this generic).
    demo.load(read_log_tail, outputs=output, every=5)


# --- Boot ----------------------------------------------------------------

# Kick off the pipeline in a daemon thread so Gradio starts immediately
# and the operator sees the UI without waiting for training to begin.
_thread = threading.Thread(target=run_pipeline, daemon=True, name="train-pipeline")
_thread.start()

if __name__ == "__main__":
    # HF Spaces expects the app to listen on port 7860 on 0.0.0.0.
    # share=False because the Space's external URL is fronted by HF.
    demo.queue().launch(server_name="0.0.0.0", server_port=7860, share=False)

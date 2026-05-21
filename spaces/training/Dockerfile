# Training Space Dockerfile.
#
# PyTorch 2.5 with CUDA 12.1 — matches the drivers HF Spaces ships on
# A100 / L4 / T4 hardware tiers. Switching to a newer minor release is
# safe as long as the cudnn version still resolves; pin a tagged release
# rather than `latest` to keep builds reproducible.

FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

# HF Spaces convention: an unprivileged "user" with UID 1000 owns the
# runtime filesystem. Creating it explicitly here keeps the Dockerfile
# portable to other GPU hosts (RunPod, Lambda Labs, etc.) without
# behavioural drift.
RUN useradd -m -u 1000 user && \
    apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

USER user
ENV PATH="/home/user/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1
WORKDIR /home/user

# Clone the training code at build time. The repo URL is intentionally
# hard-coded here — rebuild the Space (push to the Space repo) when you
# want to pick up new training code from GitHub.
RUN git clone --depth 1 https://github.com/Vsinghk523/Bharat-Agri-Lens.git repo

# Install training deps (torch + torchvision come from the base image so
# we skip them to avoid re-resolving cuda wheels).
RUN pip install --no-cache-dir --user \
    "transformers>=4.45.0" \
    "peft>=0.13.0" \
    "pillow>=10.4.0" \
    "numpy>=1.26" \
    "tqdm>=4.66" \
    "pyyaml>=6.0" \
    "onnx>=1.17.0" \
    "onnxruntime>=1.19.0" \
    "scikit-learn>=1.5.0" \
    "albumentations>=1.4.0" \
    "huggingface_hub>=0.27.0" \
    "hf_transfer>=0.1.8" \
    "gradio==4.44.1"

# Install the project so `bal-train` / `bal-export` console scripts work.
RUN pip install --no-cache-dir --user -e /home/user/repo/services/training

# The orchestration entrypoint (this file lives in the Space repo, not
# the GitHub repo, so it's COPYed in rather than pulled by the clone).
COPY --chown=user app.py /home/user/app.py

# HF Spaces routes external traffic to port 7860. Gradio listens here.
EXPOSE 7860

WORKDIR /home/user
CMD ["python", "app.py"]

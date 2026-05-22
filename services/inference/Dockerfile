# Dockerfile for the inference service.
#
# Why a Dockerfile when Railway also auto-detects Python:
# Railway's Railpack runs ``uv sync --locked`` when ``uv.lock`` is
# present, which is too rigid for our extras-bearing pyproject layout —
# without the [ml] extra installed, the real predictor crashes on
# import. Owning the build steps explicitly removes ambiguity.

FROM python:3.13-slim

WORKDIR /app

# Build tooling some pip wheels still need at install time (PIL, numpy
# fall-throughs to source on a few obscure platforms). slim, then
# pruned after install so the final image stays compact.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the files needed to resolve and install dependencies first,
# so Docker's layer cache survives most application-code edits.
COPY pyproject.toml README.md ./

# Install the project + ml extras (onnxruntime, huggingface_hub, boto3,
# pillow, numpy). hatchling needs the package source present to perform
# an editable install, so we copy `app/` before the pip call.
COPY app ./app
RUN pip install --no-cache-dir -e .[ml]

# Railway sets $PORT at runtime; the default matches the service's
# expected dev port for local docker runs.
ENV PORT=8001 \
    PYTHONUNBUFFERED=1
EXPOSE 8001

# Use the shell form so $PORT interpolates. uvicorn is now on PATH from
# the editable install above.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}

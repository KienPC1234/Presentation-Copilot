# Stage 1: build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# System packages needed for whisper / audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# "true" installs the CUDA runtime/cuBLAS/cuDNN wheels so faster-whisper can use
# a GPU. Pass INSTALL_CUDA=false for a smaller CPU-only image (docker-compose.yml
# defaults to true because this project is GPU-first).
ARG INSTALL_CUDA=true

COPY requirements-gpu.txt .
RUN if [ "$INSTALL_CUDA" = "true" ]; then \
        pip install --no-cache-dir --prefix=/install -r requirements-gpu.txt; \
    else \
        echo "[build] Skipping CUDA wheels (INSTALL_CUDA=$INSTALL_CUDA)"; \
    fi


# Stage 2: runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system packages. libgomp1 is required by ctranslate2 (faster-whisper).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Make pip-installed CUDA libraries discoverable by ctranslate2. Harmless when
# the CUDA wheels are absent, and overridable if you prefer a base CUDA image.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib

# Copy application source
COPY . .

# Data layout plus the read-only host mount point the admin panel browses.
RUN mkdir -p /app/data/docs /app/data/chroma /app/data/tmp /app/data/exports /host

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8765

# /health is public, so the probe does not need the bearer token.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
# --no-access-log drops uvicorn's per-request lines (the Docker healthcheck would
# otherwise flood the log every 30s); the app logs meaningful requests itself.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log"]

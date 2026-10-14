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


# Stage 2: minimal runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create data directories so volume mounts work cleanly
RUN mkdir -p /app/data/docs /app/data/chroma

EXPOSE 8765

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]


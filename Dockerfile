FROM python:3.11-slim

LABEL maintainer="HARINARAYANAN U <hari.narayanan1402@gmail.com>"
LABEL description="queuectl - Production-grade CLI-based background job queue system"
LABEL version="2.0.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Install queuectl
RUN pip install -e .

# Create data directory
RUN mkdir -p /data/.queuectl

# Set environment variables
ENV QUEUECTL_DB_PATH=/data/.queuectl/queuectl.db
ENV PYTHONUNBUFFERED=1

# Expose dashboard port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD queuectl status || exit 1

# Default command: show help
CMD ["queuectl", "--help"]

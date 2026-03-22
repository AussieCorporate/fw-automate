FROM python:3.11-slim

# System deps for playwright + general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY config.yaml .
COPY flatwhite/ flatwhite/
COPY start.sh .

# Install Python deps
RUN pip install --no-cache-dir -e .

# Install playwright browsers (needed for ATS scraping signals)
RUN playwright install --with-deps chromium

# Create data directory (will be overridden by persistent storage mount)
RUN mkdir -p /data

# HF Spaces runs as user 1000
RUN chmod +x start.sh && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /data
USER appuser

# HF Spaces expects port 7860
EXPOSE 7860

CMD ["./start.sh"]

# ── Bitcoin Transcription Engine ──────────────────────────────────────────────
# Use slim Python image for a smaller footprint
FROM python:3.11-slim

# Install system dependencies:
#   ffmpeg   - audio/video processing
#   curl     - used in health checks
#   gcc      - needed to compile some Python packages (e.g. psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements first to leverage layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir --timeout=300 -r requirements.txt

# Copy the rest of the application
COPY . .

# Install the package itself (provides tstbtc / tstbtc-server entry points)
RUN pip install --no-cache-dir .
# Uncomment to include local Whisper support:
# RUN pip install --no-cache-dir .[whisper]

# Expose the FastAPI port
EXPOSE 8000

# Default: run the FastAPI server via uvicorn
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
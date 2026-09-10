# Use Python 3.10 as the base image
FROM python:3.10

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Set the working directory
WORKDIR /app

# Copy requirements file first to leverage caching
COPY requirements.txt /app/requirements.txt

# Install dependencies
# This layer is cached if requirements don't change
RUN pip install --no-cache-dir --timeout=300 -r /app/requirements.txt

# Copy the rest of the application
# Done after installing deps to preserve caching
COPY . /app

# Install the package itself
# Includes the tstbtc-server entry point
RUN pip install --no-cache-dir .
# To include Whisper and/or VibeVoice support, uncomment:
# RUN pip install --no-cache-dir .[all]
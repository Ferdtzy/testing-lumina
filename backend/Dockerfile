# ── Backend Dockerfile (Django) ──────────────────────────────────────────────
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# OpenCV/PaddleOCR need OpenGL and GLib even for image-only processing.
# Include the Qt platform dependencies shipped with opencv-contrib-python.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libice6 \
    poppler-utils \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies with pip caching enabled (CPU-only PyTorch to save ~5GB)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Copy warmup script and entrypoint
COPY warmup.py .
COPY entrypoint.sh .

# Expose Django development server port
EXPOSE 8000

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
# Production: gunicorn; Development: runserver
CMD ["sh", "-c", "python manage.py migrate && gunicorn lumina.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]

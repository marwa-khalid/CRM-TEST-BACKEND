FROM python:3.11-slim

WORKDIR /app

# System deps required by OpenCV / EasyOCR / WeasyPrint
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations then start server.
# Bind to the platform-provided $PORT (Render/Railway set this); fall back to 8000 locally.
CMD alembic -c alembic.ini upgrade head && \
    uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}

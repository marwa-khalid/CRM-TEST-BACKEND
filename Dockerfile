FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app/src
ENV MPLCONFIGDIR=/tmp/matplotlib

# System deps: OpenCV / EasyOCR / WeasyPrint (libgl1, glib, pango, cairo),
# plus tesseract-ocr (pytesseract, used for scanned-PDF OCR fallback) and
# poppler-utils (pdf2image.convert_from_path / pdfinfo). Without these the
# scanned-PDF OCR path raises TesseractNotFoundError and the import job fails.
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads

EXPOSE 8000

# Run migrations then start server.
# Bind to the platform-provided $PORT (Render/Railway set this); fall back to 8000 locally.
CMD alembic -c alembic.ini upgrade head && \
    uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}

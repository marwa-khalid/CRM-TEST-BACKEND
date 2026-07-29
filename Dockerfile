FROM python:3.11-slim-trixie AS tesseract-build

ARG TESSERACT_VERSION=5.5.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf \
    autoconf-archive \
    automake \
    build-essential \
    ca-certificates \
    libarchive-dev \
    libcurl4-openssl-dev \
    libicu-dev \
    libleptonica-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    libpng-dev \
    libtiff-dev \
    libtool \
    libwebp-dev \
    pkg-config \
    wget \
    zlib1g-dev \
    && wget -q -O /tmp/tesseract.tar.gz "https://github.com/tesseract-ocr/tesseract/archive/refs/tags/${TESSERACT_VERSION}.tar.gz" \
    && tar -xzf /tmp/tesseract.tar.gz -C /tmp \
    && cd "/tmp/tesseract-${TESSERACT_VERSION}" \
    && ./autogen.sh \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && /usr/local/bin/tesseract --version


FROM python:3.11-slim-trixie

WORKDIR /app
ENV PYTHONPATH=/app/src
ENV MPLCONFIGDIR=/tmp/matplotlib
ENV PATH=/usr/local/bin:$PATH
# Use the exact eng.traineddata bundled in the repo (identical to the dev Mac's
# Homebrew model) instead of Debian's own — the language model is what makes OCR
# byte-for-byte reproducible across machines, independent of the engine build.
ENV TESSDATA_PREFIX=/app/src/fleet/assets/tessdata

COPY --from=tesseract-build /usr/local /usr/local

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
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads

EXPOSE 8000

# Run migrations then start server.
# Bind to the platform-provided $PORT (Render/Railway set this); fall back to 8000 locally.
CMD alembic -c alembic.ini upgrade head && \
    uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}

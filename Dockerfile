FROM python:3.12-slim

# Tesseract OCR (+ English / Simplified Chinese / Portuguese data) for the
# fallback that handles broken-text-layer and scanned PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package and its dependencies.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Public/hosted mode: bring-your-own-key only — keys are sent per request and
# never written to or read from the server. (Override to "0" for a private,
# single-user deployment where a machine-saved key is acceptable.)
ENV PDFTRANSLATOR_BYOK_ONLY=1

# Most platforms inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn pdftranslator.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV SECRET_KEY=dev-change-me-in-production

COPY requirements.txt .
# xhtml2pdf → svglib → rlpycairo → pycairo (needs gcc + Cairo headers to build on slim)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        pkg-config \
        libcairo2-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc libcairo2-dev pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Flask uses app.instance_path (/app/instance) for SQLite by default.
RUN mkdir -p /app/instance
VOLUME ["/app/instance"]

EXPOSE 5000

CMD ["python", "run.py"]

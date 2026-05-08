FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV SECRET_KEY=dev-change-me-in-production

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Flask uses app.instance_path (/app/instance) for SQLite by default.
RUN mkdir -p /app/instance
VOLUME ["/app/instance"]

EXPOSE 5000

CMD ["python", "run.py"]

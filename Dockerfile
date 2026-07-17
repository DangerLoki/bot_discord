FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Volumes externos para persistir dados entre reinicios
VOLUME ["/app/data", "/app/cache", "/app/config", "/app/logs"]

CMD ["python", "main.py"]
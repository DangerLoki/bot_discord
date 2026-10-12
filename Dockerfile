FROM node:22-alpine AS activity-build

WORKDIR /activity
COPY activity/package.json activity/package-lock.json ./
RUN npm ci
COPY activity/index.html activity/vite.config.js ./
COPY activity/src ./src
RUN npm run build

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=activity-build /activity/dist /app/activity/dist

# Volumes externos para persistir dados entre reinicios
VOLUME ["/app/data", "/app/cache", "/app/config", "/app/logs"]
EXPOSE 8080

CMD ["python", "main.py"]

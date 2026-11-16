FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_BUNDLE_DIR=/data/web_bundles

COPY requirements-core.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY src ./src
COPY backend ./backend

# Create default persistent volume paths
RUN mkdir -p /data/.fastf1-cache /data/web_bundles .fastf1-cache computed_data

EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]

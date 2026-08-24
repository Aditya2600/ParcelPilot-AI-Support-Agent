FROM python:3.12-slim

# Runtime-only system deps: libgomp1 is required by torch/sentence-transformers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY main.py ./main.py

# Non-root runtime user. The embedding model cache and any writable app state
# live under /home/appuser so this user can own them without a chown of /app.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /home/appuser/.cache/parcelpilot/models \
    && chown -R appuser:appuser /home/appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# Single worker: pending-action confirmation state lives in Postgres, so this is
# not required for correctness, but it keeps ingest-on-startup (embedding model
# load, migrations) from running redundantly in multiple processes.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

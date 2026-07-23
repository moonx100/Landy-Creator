# LANDY Creator API — production Docker image
#
# Build context: artifacts/landy-api/
# docker build -t landy-api .
# docker run -p 8080:8080 --env-file ../../.env landy-api

FROM python:3.11-slim

# Non-root user for security
RUN useradd --create-home --shell /bin/bash landy
WORKDIR /home/landy/app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Drop to non-root
USER landy

EXPOSE 8080

# Production: single worker, explicit host and port.
# For local dev with live reload, override CMD with:
#   uvicorn landy.main:app --host 0.0.0.0 --port 8080 --reload
CMD ["uvicorn", "landy.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

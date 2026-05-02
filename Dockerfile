# Dockerfile — FastAPI backend
#
# Build:  docker build -t substation-health-api .
# Run:    docker run -p 5000:5000 --env-file .env -v /path/to/wallet:/app/wallet substation-health-api
#
# Notes:
#   - Wallet files are mounted at runtime via -v, not baked into the image.
#     Never COPY wallet files into a Docker image.
#   - All secrets (OCI creds, Azure keys, Fulcrum key) are passed via --env-file.
#   - Set MOCK_MODE=true in .env to run without real Oracle/Azure connections.

FROM python:3.10-slim

# Install Oracle Instant Client dependencies (required for python-oracledb thick mode)
# In thin mode (default in this project) these are not needed — kept for flexibility.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ .

# Copy sample data (used when MOCK_MODE=true)
COPY sample_data/ /app/sample_data/

# Wallet is NOT copied — mount it at runtime:
#   docker run -v /host/path/to/wallet:/app/wallet ...
RUN mkdir -p /app/wallet

EXPOSE 5000

# Use a non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]

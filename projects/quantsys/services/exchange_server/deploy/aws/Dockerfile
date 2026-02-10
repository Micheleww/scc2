# Dockerfile for Exchange Server
FROM python:3.11-slim

WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire codebase
COPY . .

# Create necessary directories
RUN mkdir -p /app/tools/exchange_server/config /app/tools/exchange_server/logs

# Expose the service port
EXPOSE 8080

# Set the entry point
CMD ["python", "-m", "tools.exchange_server.main"]

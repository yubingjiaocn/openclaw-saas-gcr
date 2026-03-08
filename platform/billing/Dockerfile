FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    boto3 \
    sqlalchemy \
    asyncpg

# Copy application code
COPY *.py .

# Default command (can be overridden)
CMD ["python", "consumer.py"]

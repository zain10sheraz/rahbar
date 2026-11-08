FROM python:3.12-slim

# Prevent python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Create a non-root group and user
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/sh -d /app appuser

# Install dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Own app files by non-root user
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

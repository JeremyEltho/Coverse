FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first, so code changes do not invalidate the layer.
COPY pyproject.toml ./
COPY coverse ./coverse
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "coverse.main:app", "--host", "0.0.0.0", "--port", "8000"]

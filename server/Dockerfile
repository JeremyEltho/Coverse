FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first, so code changes do not invalidate the layer.
COPY pyproject.toml ./
COPY coverse ./coverse
RUN pip install --no-cache-dir .

EXPOSE 8000
# Shell form on purpose: hosted platforms assign a port at runtime through
# $PORT, and the container has to bind whatever it is given rather than a
# baked-in number. Falls back to 8000 for plain `docker run`.
CMD uvicorn coverse.main:app --host 0.0.0.0 --port ${PORT:-8000}

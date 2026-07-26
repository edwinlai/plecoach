FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/plecoach /app/plecoach
COPY backend/tests /app/tests

RUN pip install --no-cache-dir ".[test]"

EXPOSE 8000

CMD ["uvicorn", "plecoach.api:app", "--host", "0.0.0.0", "--port", "8000"]

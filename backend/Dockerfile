FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Apply migrations, create seed users, import the seed episodes (both safe to
# repeat on every start), then start the API. Uvicorn's access log is off because
# our own middleware writes one JSON line per request.
CMD ["sh", "-c", "alembic upgrade head && python -m cli seed-users && python -m cli import /seed/episodes.csv --summary && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]

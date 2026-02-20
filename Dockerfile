FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data /podcasts

ENV PLEX_URL=http://localhost:32400
ENV PLEX_TOKEN=""
ENV SCHEDULE_HOUR=6
ENV SCHEDULE_MINUTE=0
ENV DATABASE_PATH=/data/plex_daily_drive.db

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "120", "wsgi:app"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
RUN chmod +x /app/scripts/start-web.sh /app/scripts/start-worker.sh /app/scripts/deploy-migrate.sh

EXPOSE 8000

CMD ["/app/scripts/start-web.sh"]

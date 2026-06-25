FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && if [ \"${LUME_SEED_DEMO:-True}\" = \"True\" ]; then python manage.py seed_demo; fi && python manage.py runserver 0.0.0.0:8000"]

FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY entrypoint.sh start-web.sh start-worker.sh .
RUN chmod +x entrypoint.sh start-web.sh start-worker.sh

ENTRYPOINT ["./entrypoint.sh"]

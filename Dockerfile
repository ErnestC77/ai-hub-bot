FROM node:20-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Node не нужен в рантайме — фронтенд уже собран на предыдущей стадии.
COPY --from=frontend-build /frontend/dist frontend/dist

ENTRYPOINT ["./entrypoint.sh"]

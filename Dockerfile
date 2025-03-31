FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей для psycopg2
RUN apt-get update \
    && apt-get install -y \
        gcc \
        postgresql-server-dev-all \
        python3-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Сначала копируем только requirements.txt
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Теперь копируем все файлы проекта
COPY . .

CMD [ "python", "main.py" ]
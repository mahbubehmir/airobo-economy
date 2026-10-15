FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tehran \
    DATA_DIR=/app/data \
    OUTPUT_DIR=/app/output \
    DATABASE_PATH=/app/data/rebar_observatory.sqlite3
WORKDIR /app
EXPOSE 8501
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data /app/output
CMD ["python", "-u", "main.py"]

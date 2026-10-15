FROM python:3.11-slim

WORKDIR /app

# 安裝依賴
# yolab-quote 從 git tag 安裝，slim 映像沒有 git：只在這一步安裝，同一層移除
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

# 複製程式碼
COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "src.app:app"]

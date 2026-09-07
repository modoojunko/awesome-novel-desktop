FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 品牌单源（brand-name-single-source）：brand.json 在仓库根、不在本构建上下文，
# 由 compose additional_contexts 以命名上下文 brand 注入（brand.py 同层命中）
COPY --from=brand brand.json /app/brand.json
# CloudBase Cloud Run injects PORT env var; default 8000 for local dev
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

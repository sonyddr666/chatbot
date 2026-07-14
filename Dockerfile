# Multi-stage build
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
COPY scripts/resolve_build_host.py /tmp/resolve_build_host.py
ARG PYTORCH_VERSION=2.6.0
RUN python /tmp/resolve_build_host.py download.pytorch.org && \
    pip install --user --no-cache-dir --retries 8 --timeout 60 \
    "torch==${PYTORCH_VERSION}" \
    --index-url https://download.pytorch.org/whl/cpu
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

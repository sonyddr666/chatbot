# syntax=docker/dockerfile:1
# Multi-stage build
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
COPY scripts/download_build_wheel.py /tmp/download_build_wheel.py
ARG PYTORCH_WHEEL_URL="https://download-r2.pytorch.org/whl/cpu/torch-2.6.0%2Bcpu-cp312-cp312-linux_x86_64.whl#sha256=59e78aa0c690f70734e42670036d6b541930b8eabbaa18d94e090abf14cc4d91"
RUN --mount=type=cache,target=/root/.cache/chatbot-wheels \
    --mount=type=cache,target=/root/.cache/pip \
    python /tmp/download_build_wheel.py "${PYTORCH_WHEEL_URL}" --output "/root/.cache/chatbot-wheels/torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl" && \
    pip install --user "/root/.cache/chatbot-wheels/torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl"
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

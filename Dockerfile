# Multi-stage build
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
COPY scripts/download_build_wheel.py /tmp/download_build_wheel.py
ARG PYTORCH_WHEEL_URL="https://download-r2.pytorch.org/whl/cpu/torch-2.6.0%2Bcpu-cp312-cp312-linux_x86_64.whl#sha256=59e78aa0c690f70734e42670036d6b541930b8eabbaa18d94e090abf14cc4d91"
RUN python /tmp/download_build_wheel.py "${PYTORCH_WHEEL_URL}" --output /tmp/torch.whl && \
    pip install --user --no-cache-dir /tmp/torch.whl && \
    rm -f /tmp/torch.whl
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY configs ./configs
COPY src ./src
COPY driver.py ./

RUN pip install --no-cache-dir -e ".[genie]"

ENV PYTHONPATH=/app/src
ENV MINERU_MODEL_SOURCE=huggingface

CMD ["python", "driver.py"]

FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    python3-dev \
    gcc \
    libjpeg-dev \
    libfreetype6-dev \
    python3-spidev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY run.py /run.py

CMD ["python", "/run.py"]


RUN apt-get update && apt-get install -y \
    python3-dev \
    gcc \
    libjpeg-dev \
    libfreetype6-dev \
    python3-spidev \
    && rm -rf /var/lib/apt/lists/*
ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8

RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    curl

WORKDIR /app

COPY app/requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages --upgrade pip \
    && python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app/*.py ./
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 60099/tcp

CMD ["/run.sh"]

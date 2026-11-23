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

# 연금복권720+ 구매용 헤드리스 크로미움. Alpine chromium 은 amd64/aarch64 에서만
# 제공되므로 해당 아키텍처에서만 설치하고, armv7 등에서는 건너뛴다(구매 기능만 비활성,
# 조회·로또645 등 나머지는 정상 동작). font/media 는 런타임에 차단하지만 렌더 안정성을
# 위해 기본 폰트(ttf-freefont)와 nss/freetype/harfbuzz 를 함께 설치한다.
ARG BUILD_ARCH
RUN if [ "${BUILD_ARCH}" = "amd64" ] || [ "${BUILD_ARCH}" = "aarch64" ]; then \
        apk add --no-cache chromium nss freetype harfbuzz ca-certificates ttf-freefont \
        && echo "chromium installed for ${BUILD_ARCH}"; \
    else \
        echo "chromium not available on ${BUILD_ARCH}; pension720 purchase disabled"; \
    fi

WORKDIR /app

COPY app/requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages --upgrade pip \
    && python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app/*.py ./
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 60099/tcp

CMD ["/run.sh"]

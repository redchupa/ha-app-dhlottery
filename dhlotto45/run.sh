#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Lotto 45 Add-on v2.11.0 (Multi-Account)..."

# Build accounts JSON (최대 4계정). 비밀번호에 " \ 등 특수문자가 있어도 깨지지 않도록
# 문자열을 이어 붙이지 않고 jq 로 options.json 에서 직접 만든다.
MAX_ACCOUNTS=4
ACCOUNT_COUNT=$(jq '.accounts | length' /data/options.json)
bashio::log.info "Total accounts configured: ${ACCOUNT_COUNT} (max allowed: ${MAX_ACCOUNTS})"
if [ "${ACCOUNT_COUNT}" -gt "${MAX_ACCOUNTS}" ]; then
    bashio::log.warning "Configured ${ACCOUNT_COUNT} accounts, exceeding the maximum of ${MAX_ACCOUNTS}. Only the first ${MAX_ACCOUNTS} accounts will be loaded."
fi
ACCOUNTS_JSON=$(jq -c --argjson max "${MAX_ACCOUNTS}" \
    '[.accounts[:$max][] | {username: (.username // ""), password: (.password // ""), enabled: (if .enabled == null then true else .enabled end)}]' \
    /data/options.json)
i=0
for U in $(echo "${ACCOUNTS_JSON}" | jq -r '.[].enabled'); do
    i=$((i+1))
    bashio::log.info "  Account_${i} (enabled: ${U})"
done

export ACCOUNTS="${ACCOUNTS_JSON}"
bashio::log.info "Accounts JSON built successfully"

# 로또6/45·연금복권720+·MQTT 사용과 갱신 주기(3600초)는 고정값이다(설정 옵션 없음, main.py).

# 연금복권720+ 구매용 크로미움 경로 탐지(Alpine 패키지에 따라 바이너리 이름이 다름)
if command -v chromium-browser >/dev/null 2>&1; then
    export CHROMIUM_PATH="$(command -v chromium-browser)"
elif command -v chromium >/dev/null 2>&1; then
    export CHROMIUM_PATH="$(command -v chromium)"
else
    export CHROMIUM_PATH=""
    bashio::log.warning "chromium 미설치 — 연금복권 구매 비활성(조회/로또645는 정상)"
fi
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"

# MQTT 설정. 아이디를 비워 두고 Mosquitto broker 애드온을 쓰면 Supervisor 가 주는
# 접속 정보(호스트·전용 계정)를 자동으로 사용한다. 직접 입력한 값이 있으면 그 값을 우선한다.
MQTT_URL=$(bashio::config 'mqtt_url' '')
MQTT_USERNAME=$(bashio::config 'mqtt_username' '')
MQTT_PASSWORD=$(bashio::config 'mqtt_password' '')
MQTT_SOURCE="manual"
if [ -z "${MQTT_USERNAME}" ] && bashio::services.available "mqtt"; then
    MQTT_URL="mqtt://$(bashio::services mqtt 'host'):$(bashio::services mqtt 'port')"
    MQTT_USERNAME=$(bashio::services mqtt 'username')
    MQTT_PASSWORD=$(bashio::services mqtt 'password')
    MQTT_SOURCE="auto (Mosquitto broker)"
fi
if [ -z "${MQTT_URL}" ]; then
    MQTT_URL="mqtt://core-mosquitto:1883"
fi
export MQTT_URL MQTT_USERNAME MQTT_PASSWORD

# Home Assistant URL
export HA_URL="http://supervisor/core"

bashio::log.info "Configuration loaded:"
bashio::log.info "  Update interval: 3600s (fixed)"
bashio::log.info "  Pension720 chromium: ${CHROMIUM_PATH:-none}"
bashio::log.info "  MQTT: ${MQTT_URL} (${MQTT_SOURCE}, user: $([ -n "${MQTT_USERNAME}" ] && echo set || echo empty))"

# Run Python application
bashio::log.info "Starting application..."
cd /app
python3 -u /app/main.py

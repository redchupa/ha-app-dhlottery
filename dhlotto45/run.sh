#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Lotto 45 Add-on v2.4.8 (Multi-Account)..."

# Build accounts JSON array properly (최대 4계정 제한)
MAX_ACCOUNTS=4
ACCOUNT_COUNT=$(bashio::config 'accounts | length')
bashio::log.info "Total accounts configured: ${ACCOUNT_COUNT} (max allowed: ${MAX_ACCOUNTS})"

if [ "${ACCOUNT_COUNT}" -gt "${MAX_ACCOUNTS}" ]; then
    bashio::log.warning "Configured ${ACCOUNT_COUNT} accounts, exceeding the maximum of ${MAX_ACCOUNTS}. Only the first ${MAX_ACCOUNTS} accounts will be loaded."
    ACCOUNT_COUNT=${MAX_ACCOUNTS}
fi

# Build JSON array manually
ACCOUNTS_JSON="["
for i in $(seq 0 $((ACCOUNT_COUNT - 1))); do
    USERNAME=$(bashio::config "accounts[${i}].username")
    PASSWORD=$(bashio::config "accounts[${i}].password")
    ENABLED=$(bashio::config "accounts[${i}].enabled")
    
    # Default enabled to true if not set
    if [ -z "${ENABLED}" ] || [ "${ENABLED}" == "null" ]; then
        ENABLED="true"
    fi
    
    MASKED_USER="${USERNAME:0:2}***"
    bashio::log.info "  Account $((i+1)): ${MASKED_USER} (enabled: ${ENABLED})"
    
    # Add to JSON array
    if [ $i -gt 0 ]; then
        ACCOUNTS_JSON="${ACCOUNTS_JSON},"
    fi
    ACCOUNTS_JSON="${ACCOUNTS_JSON}{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\",\"enabled\":${ENABLED}}"
done
ACCOUNTS_JSON="${ACCOUNTS_JSON}]"

export ACCOUNTS="${ACCOUNTS_JSON}"
bashio::log.info "Accounts JSON built successfully"

# Other configuration
export ENABLE_LOTTO645=$(bashio::config 'enable_lotto645')
export ENABLE_PENSION720=$(bashio::config 'enable_pension720')
export UPDATE_INTERVAL=$(bashio::config 'update_interval')

# 연금복권720+ 구매용 크로미움 경로 탐지(Alpine 패키지에 따라 바이너리 이름이 다름)
if command -v chromium-browser >/dev/null 2>&1; then
    export CHROMIUM_PATH="$(command -v chromium-browser)"
elif command -v chromium >/dev/null 2>&1; then
    export CHROMIUM_PATH="$(command -v chromium)"
else
    export CHROMIUM_PATH=""
    bashio::log.warning "chromium 미설치 — 연금복권 구매 비활성(조회/로또645는 정상)"
fi
export USE_MQTT=$(bashio::config 'use_mqtt')
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"

# MQTT configuration (optional)
export MQTT_URL=$(bashio::config 'mqtt_url' 'mqtt://homeassistant.local:1883')
export MQTT_USERNAME=$(bashio::config 'mqtt_username' '')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password' '')

# Home Assistant URL
export HA_URL="http://supervisor/core"

bashio::log.info "Configuration loaded:"
bashio::log.info "  Update interval: ${UPDATE_INTERVAL}s"
bashio::log.info "  Lotto 645 enabled: ${ENABLE_LOTTO645}"
bashio::log.info "  Pension720 enabled: ${ENABLE_PENSION720} (chromium: ${CHROMIUM_PATH:-none})"
bashio::log.info "  Use MQTT: ${USE_MQTT}"

if bashio::config.true 'use_mqtt'; then
    bashio::log.info "  MQTT URL: ${MQTT_URL}"
fi

# Run Python application
bashio::log.info "Starting application..."
cd /app
python3 -u /app/main.py

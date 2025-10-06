#!/usr/bin/with-contenv bashio
set -eu

# 读取 add-on 配置
TARGET_HOST="$(bashio::config 'target_host')"
MQTT_HOST="$(bashio::config 'mqtt_host')"
TARGET_SCHEME="$(bashio::config 'target_scheme')"
UPSTREAM_IP="$(bashio::config 'upstream_ip')"
LOG_LEVEL_RAW="$(bashio::config 'log_level' 2>/dev/null || echo 'INFO')"
LOG_LEVEL="$(echo "${LOG_LEVEL_RAW}" | tr '[:lower:]' '[:upper:]')"

if [ -z "${TARGET_HOST}" ]; then
  bashio::log.fatal "target_host 不能为空（请在加载项配置里填写）"
  exit 1
fi
if [ -z "${MQTT_HOST}" ]; then
  bashio::log.warning "mqtt_host 为空，回退 127.0.0.1（可在配置里填内网 MQTT 地址）"
  MQTT_HOST="127.0.0.1"
fi
if [ -z "${UPSTREAM_IP}" ]; then
  bashio::log.fatal "upstream_ip 不能为空（请在加载项配置里填写）"
  exit 1
fi

export TARGET_HOST
export MQTT_HOST
export TARGET_SCHEME
export UPSTREAM_IP
export LOG_LEVEL

bashio::log.level "${LOG_LEVEL}"
bashio::log.info "Proxy configured: target_host=${TARGET_HOST}, mqtt_host=${MQTT_HOST}, target_scheme=${TARGET_SCHEME}, upstream_ip=${UPSTREAM_IP}, log_level=${LOG_LEVEL}"
bashio::log.info "Starting Fotile Proxy Server..."

# 启动你的服务（确认 /app/fotile_bridge.py 存在）
exec python3 /app/fotile_bridge.py
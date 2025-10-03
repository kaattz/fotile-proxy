#!/usr/bin/with-contenv bashio
set -e

# 读取 add-on 配置
TARGET_HOST="$(bashio::config 'target_host')"

if [ -z "${TARGET_HOST}" ]; then
  bashio::log.fatal "The 'target_host' option is not configured. Please set it in the add-on options."
  exit 1
fi

bashio::log.info "Proxy configured to target host: ${TARGET_HOST}"
bashio::log.info "Starting Fotile Proxy Server..."

# 如果你的 Python 脚本要读这个变量，可导出
export TARGET_HOST

# 启动你的服务（确认 /app/fotile_bridge.py 存在）
exec python3 /app/fotile_bridge.py
#!/bin/bash
set -e

# 从 Supervisor 提供的配置 JSON 文件中读取 target_host 的值
# bashio::config 是一个由 Home Assistant 提供的 shell 库函数
export TARGET_HOST=$(bashio::config 'target_host')

# 检查用户是否配置了 target_host
if [ -z "${TARGET_HOST}" ]; then
  bashio::log.fatal "The 'target_host' option is not configured. Please set the target server IP in the add-on configuration."
  exit 1
fi

# 打印日志，确认配置已读取
bashio::log.info "Proxy configured to target host: ${TARGET_HOST}"
bashio::log.info "Starting Fotile Proxy Server..."

# 执行 Python 脚本
exec python3 /app/fotile_bridge.py
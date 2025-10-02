# 使用 Home Assistant 官方提供的 Python 基础镜像
ARG BUILD_FROM
FROM ${BUILD_FROM}

# 设置环境变量，确保 Python 输出不会被缓冲，日志能实时显示
ENV PYTHONUNBUFFERED=1

# 更新包管理器并安装 httpx 库
# hadolint ignore=DL3008
RUN apk add --no-cache python3 py3-pip && \
    pip install --no-cache-dir --prefer-binary httpx

# 将我们当前目录下的所有文件复制到 Docker 容器的 /app 目录中
COPY . /app

# 设置工作目录为 /app
WORKDIR /app

# 赋予 run.sh 文件执行权限
RUN chmod a+x /app/run.sh

# 当容器启动时，执行 run.sh 脚本
CMD [ "/app/run.sh" ]
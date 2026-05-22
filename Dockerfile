# Tent OS Docker 镜像
# 支持 all-in-one 模式（supervisor 管理多 worker）和 multi-service 模式

FROM python:3.12-slim

# 安装系统依赖：supervisor（进程管理）、docker（沙箱化用）、curl（健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 工作目录
WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层
COPY pyproject.toml ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 复制项目代码
COPY tent_os/ ./tent_os/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY skills/ ./skills/
COPY workspace/ ./workspace/

# 创建数据目录
RUN mkdir -p /app/data /app/logs

# 设置环境变量默认值
ENV TENT_OS_DATA_DIR=/app/data \
    TENT_OS_CONFIG=/app/config/tent_os.docker.yaml \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 暴露 API Server + Control UI 端口
EXPOSE 8000

# 入口脚本
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["all-in-one"]

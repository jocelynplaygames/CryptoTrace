#!/bin/bash

echo "🚀 启动 CryptoTrace Airflow 环境"
echo "=================================="

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker"
    exit 1
fi

# 检查docker-compose.yml是否存在
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml 文件不存在"
    exit 1
fi

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "⚠️  .env 文件不存在，创建默认配置..."
    cat > .env << EOF
# Discord Bot 配置
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here

# Kafka 配置
KAFKA_BOOTSTRAP_SERVERS=host.docker.internal:9092

# Airflow 配置
AIRFLOW_UID=50000
_AIRFLOW_WWW_USER_USERNAME=airflow
_AIRFLOW_WWW_USER_PASSWORD=airflow

# API 配置
API_HOST=0.0.0.0
API_PORT=8000
EOF
    echo "✅ 已创建 .env 文件，请编辑配置"
    echo "⚠️  请确保设置了正确的 DISCORD_BOT_TOKEN 和 DISCORD_CHANNEL_ID"
fi

# 停止现有容器
echo "🛑 停止现有容器..."
docker-compose down

# 清理旧的数据（可选）
read -p "是否清理旧的数据？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧹 清理旧数据..."
    docker-compose down -v
    docker system prune -f
fi

# 构建镜像
echo "🔨 构建 Airflow 镜像..."
docker-compose build --no-cache

# 启动基础设施服务
echo "📡 启动 Kafka 基础设施..."
docker-compose up -d zookeeper kafka kafka-ui

# 等待Kafka启动
echo "⏳ 等待 Kafka 启动..."
sleep 30

# 检查Kafka是否启动成功
echo "🔍 检查 Kafka 状态..."
if ! docker-compose ps kafka | grep -q "Up"; then
    echo "❌ Kafka 启动失败"
    docker-compose logs kafka
    exit 1
fi

# 启动Airflow服务
echo "🌪️  启动 Airflow 服务..."
docker-compose up -d airflow-init

# 等待初始化完成
echo "⏳ 等待 Airflow 初始化..."
sleep 60

# 启动其他Airflow组件
echo "🚀 启动 Airflow 组件..."
docker-compose up -d airflow-webserver airflow-scheduler airflow-worker airflow-triggerer

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 30

# 检查服务状态
echo "🔍 检查服务状态..."
docker-compose ps

# 显示访问信息
echo ""
echo "✅ CryptoTrace Airflow 环境启动完成！"
echo "=================================="
echo "🌐 Airflow Web UI: http://localhost:8080"
echo "   用户名: airflow"
echo "   密码: airflow"
echo ""
echo "📊 Kafka UI: http://localhost:8081"
echo ""
echo "📡 API 服务: http://localhost:8000"
echo ""
echo "📈 Streamlit: http://localhost:8501"
echo ""
echo "🔧 管理命令："
echo "   查看日志: docker-compose logs -f [service_name]"
echo "   停止服务: docker-compose down"
echo "   重启服务: docker-compose restart [service_name]"
echo ""
echo "⚠️  重要提醒："
echo "   1. 确保在 .env 文件中设置了正确的 Discord 配置"
echo "   2. 在 Airflow Web UI 中启用 crypto_alert_dag"
echo "   3. 检查 DAG 任务状态和日志"
echo ""
echo "🎯 下一步："
echo "   1. 访问 http://localhost:8080 登录 Airflow"
echo "   2. 找到 crypto_alert_dag 并启用它"
echo "   3. 监控任务执行状态"
echo "" 
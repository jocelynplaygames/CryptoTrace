#!/bin/bash

echo "🔍 CryptoTrace Airflow 环境监控"
echo "================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查函数
check_service() {
    local service_name=$1
    local display_name=$2
    
    if docker-compose ps $service_name | grep -q "Up"; then
        echo -e "${GREEN}✅ $display_name: 运行中${NC}"
        return 0
    else
        echo -e "${RED}❌ $display_name: 未运行${NC}"
        return 1
    fi
}

check_port() {
    local port=$1
    local service_name=$2
    
    if netstat -an 2>/dev/null | grep -q ":$port.*LISTEN" || \
       ss -tuln 2>/dev/null | grep -q ":$port"; then
        echo -e "${GREEN}✅ $service_name (端口 $port): 可访问${NC}"
        return 0
    else
        echo -e "${RED}❌ $service_name (端口 $port): 不可访问${NC}"
        return 1
    fi
}

# 检查Docker容器状态
echo -e "${BLUE}📦 Docker 容器状态:${NC}"
check_service "zookeeper" "Zookeeper"
check_service "kafka" "Kafka"
check_service "kafka-ui" "Kafka UI"
check_service "airflow-webserver" "Airflow WebServer"
check_service "airflow-scheduler" "Airflow Scheduler"
check_service "airflow-worker" "Airflow Worker"
check_service "airflow-triggerer" "Airflow Triggerer"

echo ""

# 检查端口状态
echo -e "${BLUE}🌐 端口访问状态:${NC}"
check_port "2181" "Zookeeper"
check_port "9092" "Kafka"
check_port "8081" "Kafka UI"
check_port "8080" "Airflow Web UI"
check_port "8793" "Airflow Worker"

echo ""

# 检查Kafka连接
echo -e "${BLUE}📡 Kafka 连接测试:${NC}"
if docker-compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Kafka 连接正常${NC}"
else
    echo -e "${RED}❌ Kafka 连接失败${NC}"
fi

# 检查Airflow数据库
echo -e "${BLUE}🗄️  Airflow 数据库状态:${NC}"
if docker-compose exec -T airflow-webserver airflow db check > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Airflow 数据库正常${NC}"
else
    echo -e "${RED}❌ Airflow 数据库异常${NC}"
fi

echo ""

# 检查DAG状态
echo -e "${BLUE}📋 DAG 状态:${NC}"
if docker-compose exec -T airflow-webserver airflow dags list | grep -q "crypto_alert_dag"; then
    echo -e "${GREEN}✅ crypto_alert_dag 已注册${NC}"
    
    # 检查DAG是否启用
    if docker-compose exec -T airflow-webserver airflow dags list | grep "crypto_alert_dag" | grep -q "True"; then
        echo -e "${GREEN}✅ crypto_alert_dag 已启用${NC}"
    else
        echo -e "${YELLOW}⚠️  crypto_alert_dag 未启用${NC}"
    fi
else
    echo -e "${RED}❌ crypto_alert_dag 未找到${NC}"
fi

echo ""

# 检查最近的任务执行
echo -e "${BLUE}📊 最近任务执行状态:${NC}"
docker-compose exec -T airflow-webserver airflow dags state crypto_alert_dag 2>/dev/null || echo -e "${YELLOW}⚠️  无法获取DAG状态${NC}"

echo ""

# 检查日志
echo -e "${BLUE}📝 最近错误日志:${NC}"
ERROR_LOGS=$(docker-compose logs --tail=10 airflow-scheduler 2>/dev/null | grep -i error | tail -3)
if [ -n "$ERROR_LOGS" ]; then
    echo -e "${RED}❌ 发现错误日志:${NC}"
    echo "$ERROR_LOGS"
else
    echo -e "${GREEN}✅ 未发现错误日志${NC}"
fi

echo ""

# 检查资源使用情况
echo -e "${BLUE}💾 资源使用情况:${NC}"
echo "Docker 容器内存使用:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""

# 提供管理命令
echo -e "${BLUE}🔧 管理命令:${NC}"
echo "查看所有日志: docker-compose logs -f"
echo "查看特定服务日志: docker-compose logs -f [service_name]"
echo "重启服务: docker-compose restart [service_name]"
echo "停止所有服务: docker-compose down"
echo "重新构建: docker-compose build --no-cache"
echo "清理数据: docker-compose down -v && docker system prune -f"

echo ""

# 检查环境变量
echo -e "${BLUE}⚙️  环境配置检查:${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ .env 文件存在${NC}"
    
    # 检查关键配置
    if grep -q "DISCORD_BOT_TOKEN" .env; then
        TOKEN=$(grep "DISCORD_BOT_TOKEN" .env | cut -d'=' -f2)
        if [ "$TOKEN" != "your_discord_bot_token_here" ]; then
            echo -e "${GREEN}✅ Discord Bot Token 已配置${NC}"
        else
            echo -e "${YELLOW}⚠️  Discord Bot Token 需要配置${NC}"
        fi
    else
        echo -e "${RED}❌ Discord Bot Token 未配置${NC}"
    fi
    
    if grep -q "DISCORD_CHANNEL_ID" .env; then
        CHANNEL_ID=$(grep "DISCORD_CHANNEL_ID" .env | cut -d'=' -f2)
        if [ "$CHANNEL_ID" != "your_channel_id_here" ]; then
            echo -e "${GREEN}✅ Discord Channel ID 已配置${NC}"
        else
            echo -e "${YELLOW}⚠️  Discord Channel ID 需要配置${NC}"
        fi
    else
        echo -e "${RED}❌ Discord Channel ID 未配置${NC}"
    fi
else
    echo -e "${RED}❌ .env 文件不存在${NC}"
fi

echo ""
echo -e "${BLUE}🎯 访问地址:${NC}"
echo "Airflow Web UI: http://localhost:8080 (airflow/airflow)"
echo "Kafka UI: http://localhost:8081"
echo "API 文档: http://localhost:8000/docs"
echo "Streamlit: http://localhost:8501"

echo ""
echo "✅ 监控检查完成！" 
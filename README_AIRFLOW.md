# 🚀 CryptoTrace Airflow 版本完整指南

## 📋 概述

这是 CryptoTrace 项目的 **Airflow 容器化版本**，提供了完整的加密货币监控和告警系统，支持自动化调度、任务编排和容器化部署。

## 🏗️ 架构特点

### ✅ 完整的数据管道
```
Binance API → WebSocket客户端 → Kafka生产者 → 价格处理器 → 异常检测器 → Discord机器人
     ↓              ↓              ↓              ↓              ↓              ↓
example.py    feed_client.py  crypto_producer  price_processor  anomaly_detector  alert_bot.py
```

### ✅ 容器化部署
- **Docker Compose** 一键部署
- **Airflow 2.7.1** 任务调度
- **Celery Executor** 分布式执行
- **PostgreSQL** 元数据存储
- **Redis** 消息队列

### ✅ 自动化调度
- **每15分钟** 自动执行完整数据管道
- **任务依赖管理** 确保执行顺序
- **失败重试机制** 自动处理临时错误
- **健康检查** 监控系统状态

## 🚀 快速启动

### 1. 环境准备
```bash
# 确保 Docker 和 Docker Compose 已安装
docker --version
docker-compose --version
```

### 2. 一键启动
```bash
# 使用启动脚本
./start_airflow.sh

# 或手动启动
docker-compose up -d
```

### 3. 配置环境变量
编辑 `.env` 文件：
```bash
# Discord Bot 配置
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here

# Kafka 配置
KAFKA_BOOTSTRAP_SERVERS=host.docker.internal:9092

# Airflow 配置
AIRFLOW_UID=50000
_AIRFLOW_WWW_USER_USERNAME=airflow
_AIRFLOW_WWW_USER_PASSWORD=airflow
```

### 4. 访问服务
- **Airflow Web UI**: http://localhost:8080 (airflow/airflow)
- **Kafka UI**: http://localhost:8081
- **API 文档**: http://localhost:8000/docs
- **Streamlit**: http://localhost:8501

## 📊 监控和管理

### 系统监控
```bash
# 检查系统状态
./monitor_airflow.sh

# 查看服务日志
docker-compose logs -f [service_name]

# 查看资源使用
docker stats
```

### DAG 管理
1. 访问 http://localhost:8080
2. 登录 (airflow/airflow)
3. 找到 `crypto_alert_dag`
4. 启用 DAG
5. 监控任务执行

## 🔧 组件详解

### 1. 数据采集层
- **`example.py`**: WebSocket客户端，连接Binance实时数据流
- **`crypto_producer.py`**: Kafka生产者，发送数据到消息队列

### 2. 数据处理层
- **`price_processor.py`**: 价格处理器，实时分析价格数据
- **`anomaly_detector.py`**: 异常检测器，使用统计和ML方法检测异常

### 3. 输出层
- **`alert_bot.py`**: Discord机器人，发送异常告警
- **`alert_processor.py`**: 告警处理器，处理价格阈值告警
- **`storage_consumer.py`**: 存储消费者，保存数据到文件系统

### 4. 服务层
- **`app.py`**: FastAPI服务，提供REST API
- **`streamlit_app.py`**: Streamlit可视化界面

## 📈 任务流程

### DAG 任务依赖
```
run_crypto_producer >> run_ws_feeder >> run_price_processor >> run_anomaly_detector >> run_discord_alert_bot
                                    ↓
                              run_alert_processor
                                    ↓
                              run_storage_consumer
```

### 任务配置
- **执行间隔**: 每15分钟
- **超时时间**: 30分钟
- **重试次数**: 3次
- **重试延迟**: 5分钟（指数退避）

## 🛠️ 故障排除

### 常见问题

#### 1. Kafka 连接失败
```bash
# 检查Kafka状态
docker-compose ps kafka
docker-compose logs kafka

# 重启Kafka
docker-compose restart kafka
```

#### 2. Airflow 任务失败
```bash
# 查看任务日志
docker-compose logs airflow-scheduler

# 检查DAG状态
docker-compose exec airflow-webserver airflow dags state crypto_alert_dag
```

#### 3. Discord Bot 不工作
```bash
# 检查环境变量
cat .env | grep DISCORD

# 查看Bot日志
docker-compose logs airflow-worker | grep discord
```

### 日志查看
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f airflow-scheduler
docker-compose logs -f airflow-worker
docker-compose logs -f kafka
```

## 🔄 与本地版本对比

| 特性 | 本地版本 | Airflow版本 |
|------|----------|-------------|
| 部署方式 | 手动启动脚本 | Docker容器化 |
| 任务调度 | 无 | 自动化调度 |
| 错误处理 | 基础 | 重试机制 |
| 监控 | 手动 | 健康检查 |
| 扩展性 | 有限 | 高 |
| 生产就绪 | 否 | 是 |

## 📝 开发指南

### 添加新任务
1. 在 `airflow/src/` 下创建新模块
2. 添加 `main()` 函数
3. 在 `crypto_alert_dag.py` 中添加任务
4. 设置任务依赖

### 修改配置
1. 编辑 `.env` 文件
2. 重启相关服务：`docker-compose restart [service]`

### 更新代码
1. 修改源代码
2. 重新构建镜像：`docker-compose build --no-cache`
3. 重启服务：`docker-compose up -d`

## 🎯 最佳实践

### 1. 环境管理
- 使用 `.env` 文件管理配置
- 定期备份数据
- 监控资源使用

### 2. 任务优化
- 合理设置执行间隔
- 监控任务执行时间
- 及时处理失败任务

### 3. 监控告警
- 定期运行 `monitor_airflow.sh`
- 设置Discord告警
- 监控系统资源

## 📞 支持

如有问题，请：
1. 查看日志：`docker-compose logs -f`
2. 运行监控：`./monitor_airflow.sh`
3. 检查配置：`cat .env`

---

**🎉 享受您的加密货币监控系统！** 
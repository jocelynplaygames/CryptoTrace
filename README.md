# CryptoTrace: Real-time Crypto Monitoring & Alert System

## 🚀 Installation

1️⃣ **Clone the Repository**
```bash
git clone <repository-url>
cd crypto-price-monitoring
```

2️⃣ **Setup Environment**
```bash
# Run the setup script
chmod +x setup.sh
./setup.sh
```

3️⃣ **Configure Environment**
```bash
# Update the .env file with your configuration
nano .env

# Required Environment Variables:
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
AIRFLOW_HOME=/path/to/airflow
TABLEAU_SERVER_URL=your_tableau_server_url  # Optional
```

## 🎮 Component Setup

### 1. 启动 Kafka（你已完成）
docker-compose up -d kafka

### 2. 启动 WebSocket → Kafka 数据源
python src/data_ingestion/crypto_feeds/example.py

### 3. 启动 Processor（只能选一个）：
### 选 3A：默认处理器（线程版）
python src/processing/stream_processor/price_processor.py

### 或 选 3B：高级 Flink 处理器（如果你用 Flink）
python src/processing/flink_processor/price_processor.py

### 4. 启动异常检测（从 Kafka 读 alert）
python src/processing/anomaly_detector/price_anomaly_detector.py

### 5. 启动 Discord bot（从 Kafka 读 alert）
python src/visualization/discord_bot/alert_bot.py

### 6. Apache Airflow
```bash
# Start all services using Docker Compose
docker-compose up -d

# Initialize Airflow database (if needed)
docker exec CryptoTrace-airflow-webserver-1 airflow db init

# Create default admin user (if needed)
docker exec CryptoTrace-airflow-webserver-1 airflow users create \
    --username airflow \
    --password airflow \
    --firstname admin \
    --lastname admin \
    --role Admin \
    --email admin@example.com

Access Airflow Web Interface
Open http://localhost:8080 in your browser
Login with:
- Username: airflow
- Password: airflow
```

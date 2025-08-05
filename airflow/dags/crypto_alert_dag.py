from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import subprocess
import sys
import os

# 添加你的项目代码路径（容器内路径）
sys.path.append('/opt/airflow/project-root')

# 导入直接可调用的 main 函数（推荐用法）
from src.data_ingestion.kafka_producer.crypto_producer import main as producer_main
from src.processing.stream_processor.price_processor import main as price_processor_main
from src.processing.anomaly_detector.price_anomaly_detector import main as anomaly_detector_main
from src.visualization.discord_bot.alert_bot import main as discord_alert_main
from src.storage.time_series.storage_consumer import main as storage_consumer_main
from src.alerting.alert_processor import main as alert_processor_main

# 使用主版本的 example.py，通过绝对路径导入
import sys
sys.path.append('/opt/airflow/project-root')
from src.data_ingestion.crypto_feeds.example import main as ws_feeder_main

# 改进的默认参数
default_args = {
    "start_date": datetime(2024, 1, 1),
    "catchup": False,
    "execution_timeout": timedelta(minutes=30),  # 增加超时时间
    "retries": 3,  # 增加重试次数
    "retry_delay": timedelta(minutes=5),  # 重试间隔
    "retry_exponential_backoff": True,  # 指数退避
    "max_retry_delay": timedelta(minutes=30),  # 最大重试延迟
}

with DAG(
    dag_id="crypto_alert_dag",
    schedule_interval="*/15 * * * *",  # 改为15分钟间隔，减少频率
    default_args=default_args,
    tags=["crypto", "monitoring"],
    max_active_runs=1,  # 防止重复执行
    description="Complete cryptocurrency monitoring and alerting pipeline"
) as dag:

    # 1. 数据生产者任务
    run_crypto_producer = PythonOperator(
        task_id="run_crypto_producer",
        python_callable=producer_main,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 2. WebSocket数据采集任务
    def run_unified_crypto_feed():
        """在 Airflow 中运行统一的数据流脚本"""
        import os
        # 设置 Airflow 环境变量
        os.environ['CRYPTO_FEED_MODE'] = 'airflow'
        os.environ['CRYPTO_SYMBOLS'] = 'BTC-USD,ETH-USD,SOL-USD,ADA-USD'
        os.environ['KAFKA_TOPIC'] = 'crypto-prices'
        # 运行主函数
        ws_feeder_main()
    
    run_ws_feeder = PythonOperator(
        task_id="run_ws_feeder",
        python_callable=run_unified_crypto_feed,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 3. 价格处理器任务
    run_price_processor = PythonOperator(
        task_id="run_price_processor",
        python_callable=price_processor_main,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 4. 异常检测器任务
    run_anomaly_detector = PythonOperator(
        task_id="run_anomaly_detector",
        python_callable=anomaly_detector_main,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 5. 告警处理器任务
    run_alert_processor = PythonOperator(
        task_id="run_alert_processor",
        python_callable=alert_processor_main,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 6. Discord机器人任务
    run_discord_alert_bot = PythonOperator(
        task_id="run_discord_alert_bot",
        python_callable=discord_alert_main,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 7. 存储消费者任务（并行运行）
    run_storage_consumer = PythonOperator(
        task_id="run_storage_consumer",
        python_callable=storage_consumer_main,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )

    # 8. 健康检查任务
    def health_check():
        """检查各组件健康状态"""
        import requests
        import json
        from kafka import KafkaConsumer
        
        # 检查Kafka连接
        try:
            consumer = KafkaConsumer(
                bootstrap_servers='host.docker.internal:9092',
                group_id='health_check',
                auto_offset_reset='latest'
            )
            consumer.close()
            print("✅ Kafka connection: OK")
        except Exception as e:
            print(f"❌ Kafka connection: FAILED - {e}")
            raise
        
        # 检查数据目录
        data_dir = "/opt/airflow/project-root/data"
        if os.path.exists(data_dir):
            print("✅ Data directory: OK")
        else:
            print("❌ Data directory: NOT FOUND")
        
        print("✅ Health check completed successfully")
    
    health_check_task = PythonOperator(
        task_id="health_check",
        python_callable=health_check,
        retries=1,
        retry_delay=timedelta(minutes=1),
    )

    # 设置任务依赖顺序
    # 主要数据流
    run_crypto_producer >> run_ws_feeder >> run_price_processor >> run_anomaly_detector >> run_discord_alert_bot
    
    # 并行任务
    run_price_processor >> run_alert_processor
    run_price_processor >> run_storage_consumer
    
    # 健康检查在最后
    [run_discord_alert_bot, run_alert_processor, run_storage_consumer] >> health_check_task

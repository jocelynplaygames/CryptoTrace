from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import subprocess
import sys

# 添加你的项目代码路径（容器内路径）
sys.path.append('/opt/airflow/project-root')

# 定义可运行模块或脚本的通用函数
def run_script(script_path, use_module=False):
    if use_module:
        subprocess.run(["python", "-m", script_path], check=True)
    else:
        subprocess.run(["python", script_path], check=True)

# 导入直接可调用的 main 函数（推荐用法）
from src.data_ingestion.kafka_producer.crypto_producer import main as producer_main
from src.processing.stream_processor.price_processor import main as price_processor_main
from src.processing.anomaly_detector.price_anomaly_detector import main as anomaly_detector_main
from src.visualization.discord_bot.alert_bot import main as discord_alert_main
# 使用主版本的 example.py，通过绝对路径导入
import sys
sys.path.append('/opt/airflow/project-root')
from src.data_ingestion.crypto_feeds.example import main as ws_feeder_main

default_args = {
    "start_date": datetime(2024, 1, 1),
    "catchup": False,
    "execution_timeout": timedelta(minutes=10),
    "retries": 1,
}

with DAG(
    dag_id="crypto_alert_dag",
    schedule_interval="*/5 * * * *",  # 每5分钟运行一次
    default_args=default_args,
    tags=["crypto"],
) as dag:

    run_crypto_producer = PythonOperator(
        task_id="run_crypto_producer",
        python_callable=producer_main,
    )

    # run_ws_feeder = PythonOperator(
    #     task_id="run_ws_feeder",
    #     python_callable=run_script,
    #     op_args=["src.data_ingestion.crypto_feeds.example"],
    #     op_kwargs={"use_module": True},
    # )
    # 使用统一的数据流脚本
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
    )

    run_price_processor = PythonOperator(
        task_id="run_price_processor",
        python_callable=price_processor_main,
    )

    run_anomaly_detector = PythonOperator(
        task_id="run_anomaly_detector",
        python_callable=anomaly_detector_main,
    )

    run_discord_alert_bot = PythonOperator(
        task_id="run_discord_alert_bot",
        python_callable=discord_alert_main,
    )

    # 设置任务依赖顺序
    run_crypto_producer >> run_ws_feeder >> run_price_processor >> run_anomaly_detector >> run_discord_alert_bot

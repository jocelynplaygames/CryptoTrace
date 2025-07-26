from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import subprocess

import sys
sys.path.append('/opt/airflow/project-root')

# =====================
# 加密货币监控DAG主流程
# =====================

# 通过subprocess运行脚本，支持普通脚本和模块方式
def run_script(script_path, use_module=False):
    if use_module:
        # 以模块方式运行，例如 python -m xxx
        subprocess.run(["python", "-m", script_path], check=True)
    else:
        # 以脚本方式运行，例如 python xxx.py
        # 现在script_path已经是绝对路径了
        subprocess.run(["python", script_path], check=True)

default_args = {
    "start_date": datetime(2024, 1, 1),
    "catchup": False,
    "execution_timeout": timedelta(minutes=5),  # 5分钟超时
    "retries": 1,  # 失败重试1次
}

with DAG(
    dag_id="crypto_alert_dag",
    schedule_interval=None,  # 手动运行，避免多进程乱冲突
    default_args=default_args,
    tags=["crypto"],
) as dag:

    # 1. 生产Kafka数据（推送行情到Kafka队列）
    run_crypto_producer = PythonOperator(
        task_id="run_crypto_producer",
        python_callable=run_script,
        op_args=["/opt/airflow/project-root/src/data_ingestion/kafka_producer/crypto_producer.py"]
    )

    # 2. 采集行情数据（如Websocket采集）
    run_ws_feeder = PythonOperator(
        task_id="run_ws_feeder",
        python_callable=run_script,
        op_args=["/opt/airflow/project-root/src/data_ingestion/crypto_feeds/example.py"]
    )

    # 3. 行情数据处理（如清洗、聚合等）
    run_price_processor = PythonOperator(
        task_id="run_price_processor",
        python_callable=run_script,
        op_args=["/opt/airflow/project-root/src/processing/stream_processor/price_processor.py"]
    )

    # 4. 异常检测（识别价格异常波动）
    run_anomaly_detector = PythonOperator(
        task_id="run_anomaly_detector",
        python_callable=run_script,
        op_args=["/opt/airflow/project-root/src/processing/anomaly_detector/price_anomaly_detector.py"]
    )

    # 5. 发送告警（通过Discord机器人通知）
    run_discord_alert_bot = PythonOperator(
        task_id="run_discord_alert_bot",
        python_callable=run_script,
        op_args=["/opt/airflow/project-root/src/visualization/discord_bot/alert_bot.py"]
    )

    # 设置任务依赖顺序，保证流程串联
    run_crypto_producer >> run_ws_feeder >> run_price_processor >> run_anomaly_detector >> run_discord_alert_bot

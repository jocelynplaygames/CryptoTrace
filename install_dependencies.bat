@echo off
echo === 在Airflow容器内安装Python依赖 ===

echo 1. 升级pip...
docker exec cryptotrace-airflow-webserver-1 pip install --upgrade pip

echo 2. 安装基础依赖...
docker exec cryptotrace-airflow-webserver-1 pip install six
docker exec cryptotrace-airflow-webserver-1 pip install websockets==11.0.3
docker exec cryptotrace-airflow-webserver-1 pip install python-dateutil==2.8.2
docker exec cryptotrace-airflow-webserver-1 pip install python-json-logger==2.0.7
docker exec cryptotrace-airflow-webserver-1 pip install requests==2.31.0

echo 3. 安装kafka-python...
docker exec cryptotrace-airflow-webserver-1 pip install kafka-python==2.0.2

echo 4. 安装confluent-kafka...
docker exec cryptotrace-airflow-webserver-1 pip install confluent-kafka

echo 5. 安装数据处理依赖...
docker exec cryptotrace-airflow-webserver-1 pip install numpy>=1.26.0
docker exec cryptotrace-airflow-webserver-1 pip install pandas>=2.1.0
docker exec cryptotrace-airflow-webserver-1 pip install scipy>=1.11.0

echo 6. 安装可视化依赖...
docker exec cryptotrace-airflow-webserver-1 pip install streamlit>=1.28.0
docker exec cryptotrace-airflow-webserver-1 pip install plotly>=5.17.0

echo 7. 安装其他依赖...
docker exec cryptotrace-airflow-webserver-1 pip install discord.py>=2.3.0

echo === 依赖安装完成 ===
echo 检查安装结果：
docker exec cryptotrace-airflow-webserver-1 pip list | findstr /R "kafka confluent requests numpy pandas scipy streamlit plotly discord"

pause 
#!/bin/bash

echo "=== 在Airflow容器内安装Python依赖 ==="

# 升级pip
echo "1. 升级pip..."
pip install --upgrade pip

# 安装基础依赖（先安装这些，避免冲突）
echo "2. 安装基础依赖..."
pip install six
pip install "websockets==11.0.3"
pip install "python-dateutil==2.8.2"
pip install "python-json-logger==2.0.7"
pip install "requests==2.31.0"

# 安装kafka-python
echo "3. 安装kafka-python..."
pip install "kafka-python==2.0.2"

# 安装confluent-kafka
echo "4. 安装confluent-kafka..."
pip install "confluent-kafka"

# 安装数据处理依赖
echo "5. 安装数据处理依赖..."
pip install "numpy>=1.26.0"
pip install "pandas>=2.1.0"
pip install "scipy>=1.11.0"

# 安装可视化依赖
echo "6. 安装可视化依赖..."
pip install "streamlit>=1.28.0"
pip install "plotly>=5.17.0"

# 安装其他依赖
echo "7. 安装其他依赖..."
pip install "discord.py>=2.3.0"

echo "=== 依赖安装完成 ==="
echo "检查安装结果："
pip list | grep -E "(kafka|confluent|requests|numpy|pandas|scipy|streamlit|plotly|discord)"

#!/bin/bash

# 设置错误时退出
set -e

echo "=== 在Airflow容器内安全安装Python依赖 ==="

# 函数：检查命令是否成功
check_status() {
    if [ $? -eq 0 ]; then
        echo "✓ $1 成功"
    else
        echo "✗ $1 失败"
        exit 1
    fi
}

# 升级pip
echo "1. 升级pip..."
pip install --upgrade pip
check_status "升级pip"

# 安装基础依赖
echo "2. 安装基础依赖..."
pip install six
check_status "安装six"

pip install websockets==11.0.3
check_status "安装websockets"

pip install python-dateutil==2.8.2
check_status "安装python-dateutil"

pip install python-json-logger==2.0.7
check_status "安装python-json-logger"

pip install requests==2.31.0
check_status "安装requests"

# 安装kafka-python
echo "3. 安装kafka-python..."
pip install kafka-python==2.0.2
check_status "安装kafka-python"

# 安装confluent-kafka
echo "4. 安装confluent-kafka..."
pip install confluent-kafka
check_status "安装confluent-kafka"

# 安装数据处理依赖
echo "5. 安装数据处理依赖..."
pip install numpy>=1.26.0
check_status "安装numpy"

pip install pandas>=2.1.0
check_status "安装pandas"

pip install scipy>=1.11.0
check_status "安装scipy"

# 安装可视化依赖
echo "6. 安装可视化依赖..."
pip install streamlit>=1.28.0
check_status "安装streamlit"

pip install plotly>=5.17.0
check_status "安装plotly"

# 安装其他依赖
echo "7. 安装其他依赖..."
pip install discord.py>=2.3.0
check_status "安装discord.py"

echo "=== 所有依赖安装完成 ==="
echo "检查安装结果："
pip list | grep -E "(kafka|confluent|requests|numpy|pandas|scipy|streamlit|plotly|discord)"

echo "=== 测试关键模块导入 ==="
python -c "import kafka; print('✓ kafka 导入成功')"
python -c "import confluent_kafka; print('✓ confluent_kafka 导入成功')"
python -c "import requests; print('✓ requests 导入成功')"
python -c "import numpy; print('✓ numpy 导入成功')"
python -c "import pandas; print('✓ pandas 导入成功')" 
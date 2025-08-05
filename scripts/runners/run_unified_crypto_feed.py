#!/usr/bin/env python3
"""
统一的数据流管理脚本
支持多种运行模式：独立运行、Airflow 任务、持续监控等
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.data_ingestion.crypto_feeds.example import main, ENVIRONMENT

def main_with_args():
    """带参数的主函数"""
    parser = argparse.ArgumentParser(description='加密货币数据流统一管理脚本')
    parser.add_argument(
        '--mode', 
        choices=['standalone', 'airflow', 'monitor', 'test'],
        default='standalone',
        help='运行模式：standalone(独立运行), airflow(Airflow任务), monitor(持续监控), test(测试模式)'
    )
    parser.add_argument(
        '--symbols',
        nargs='+',
        default=['BTC-USD', 'ETH-USD', 'SOL-USD', 'ADA-USD'],
        help='要监控的加密货币对列表'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=0,
        help='运行时长（秒），0表示无限运行'
    )
    parser.add_argument(
        '--kafka-topic',
        default='crypto-prices',
        help='Kafka 主题名称'
    )
    
    args = parser.parse_args()
    
    print(f"🚀 启动加密货币数据流")
    print(f"📊 运行模式: {args.mode}")
    print(f"🌍 检测环境: {ENVIRONMENT}")
    print(f"💰 监控币种: {', '.join(args.symbols)}")
    print(f"📡 Kafka 主题: {args.kafka_topic}")
    
    if args.duration > 0:
        print(f"⏱️  运行时长: {args.duration} 秒")
    
    # 设置环境变量供 example.py 使用
    os.environ['CRYPTO_FEED_MODE'] = args.mode
    os.environ['CRYPTO_SYMBOLS'] = ','.join(args.symbols)
    os.environ['KAFKA_TOPIC'] = args.kafka_topic
    
    if args.duration > 0:
        os.environ['RUN_DURATION'] = str(args.duration)
    
    # 运行主函数
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 用户中断，正在优雅关闭...")
    except Exception as e:
        print(f"❌ 运行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main_with_args() 
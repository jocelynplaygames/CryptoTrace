"""
环境配置文件
统一管理不同运行环境的配置参数
"""

import os
from typing import Dict, Any

class EnvironmentConfig:
    """环境配置管理类"""
    
    def __init__(self):
        self.environment = self._detect_environment()
        self.config = self._load_config()
    
    def _detect_environment(self) -> str:
        """检测当前运行环境"""
        if os.path.exists('/opt/airflow'):
            return 'airflow'
        elif os.getenv('DOCKER_ENV'):
            return 'docker'
        else:
            return 'local'
    
    def _load_config(self) -> Dict[str, Any]:
        """加载环境配置"""
        base_config = {
            'kafka': {
                'topic': 'crypto-prices',
                'group_id': 'crypto-monitor-group',
                'auto_offset_reset': 'latest'
            },
            'websocket': {
                'reconnect_interval': 5,
                'max_reconnect_attempts': 10
            },
            'monitoring': {
                'default_symbols': ['BTC-USD', 'ETH-USD', 'SOL-USD', 'ADA-USD'],
                'price_update_interval': 1.0
            }
        }
        
        if self.environment == 'airflow':
            # Airflow 容器环境配置
            base_config['kafka']['bootstrap_servers'] = 'kafka:29092'
            base_config['websocket']['timeout'] = 30
            base_config['logging'] = {'level': 'INFO', 'format': 'airflow'}
            
        elif self.environment == 'docker':
            # Docker 环境配置
            base_config['kafka']['bootstrap_servers'] = 'kafka:29092'
            base_config['websocket']['timeout'] = 30
            base_config['logging'] = {'level': 'INFO', 'format': 'standard'}
            
        else:
            # 本地开发环境配置
            base_config['kafka']['bootstrap_servers'] = 'localhost:9092'
            base_config['websocket']['timeout'] = 10
            base_config['logging'] = {'level': 'DEBUG', 'format': 'standard'}
        
        return base_config
    
    def get(self, key: str, default=None):
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_kafka_config(self) -> Dict[str, Any]:
        """获取 Kafka 配置"""
        return self.config['kafka']
    
    def get_websocket_config(self) -> Dict[str, Any]:
        """获取 WebSocket 配置"""
        return self.config['websocket']
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取监控配置"""
        return self.config['monitoring']
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get('logging', {'level': 'INFO', 'format': 'standard'})

# 全局配置实例
config = EnvironmentConfig() 
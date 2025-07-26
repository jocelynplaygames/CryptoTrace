
"""
Kafka producer for streaming cryptocurrency data.
Kafka生产者模块 - 用于流式传输加密货币数据
该模块负责将实时加密货币价格数据发送到Kafka消息队列中，
为后续的数据处理和分析提供数据流。
"""
# 输入：加密货币数据字典（包含symbol、price等字段）
# 输出：发送到Kafka主题的JSON消息，主题名格式为crypto_prices.{symbol}

import json
import logging
from typing import Dict, Optional
from datetime import datetime
from kafka import KafkaProducer
from kafka.errors import KafkaError

# 设置日志记录器
logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for datetime objects.
    自定义JSON编码器 - 用于处理datetime对象
    
    由于JSON标准不支持datetime类型，我们需要自定义编码器
    将datetime对象转换为ISO格式的字符串，以便JSON序列化。
    """
    def default(self, obj):
        # 如果对象是datetime类型，转换为ISO格式字符串
        if isinstance(obj, datetime):
            return obj.isoformat()
        # 对于其他类型，使用父类的默认处理方式
        return super().default(obj)

class CryptoKafkaProducer:
    """
    加密货币Kafka生产者类
    
    该类负责：
    1. 连接到Kafka消息代理
    2. 将加密货币数据序列化并发送到指定的Kafka主题
    3. 处理发送过程中的错误和异常
    4. 管理生产者的生命周期
    """
    
    # def __init__(self, bootstrap_servers: str = 'localhost:9092', topic_prefix: str = 'crypto_prices'):
    def __init__(self, bootstrap_servers: str = 'host.docker.internal:9092', topic_prefix: str = 'crypto_prices'):
        """
        Initialize the Kafka producer for cryptocurrency data.
        初始化Kafka生产者
        
        Args:
            bootstrap_servers: Kafka bootstrap servers
                              Kafka引导服务器地址
                              - 本地开发环境通常使用 'localhost:9092'
                              - Docker环境使用 'host.docker.internal:9092'
            topic_prefix: Prefix for Kafka topics (final topic will be {prefix}.{symbol})
                         Kafka主题前缀
                         - 最终主题名称将是 {prefix}.{symbol}
                         - 例如：crypto_prices.btc, crypto_prices.eth
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic_prefix = topic_prefix
        self.producer: Optional[KafkaProducer] = None  # Kafka生产者实例，初始为None
        
    def connect(self) -> bool:
        """
        Connect to Kafka broker.
        连接到Kafka消息代理
        
        该方法会：
        1. 创建KafkaProducer实例
        2. 配置序列化器（JSON格式）
        3. 设置可靠性参数（acks='all'确保数据不丢失）
        4. 配置重试机制
        
        Returns:
            bool: True if connection successful, False otherwise
            bool: 连接成功返回True，失败返回False
        """
        try:
            # 创建Kafka生产者实例，配置各种参数
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,  # Kafka服务器地址
                value_serializer=lambda v: json.dumps(v, cls=DateTimeEncoder).encode('utf-8'),  # 值序列化器
                key_serializer=lambda v: v.encode('utf-8'),  # 键序列化器
                acks='all',  # Wait for all replicas - 等待所有副本确认，确保数据不丢失
                retries=3,   # Retry on failure - 发送失败时重试3次
                max_in_flight_requests_per_connection=1  # Preserve order - 每个连接最多1个未完成请求，保证消息顺序
            )
            logger.info(f"Connected to Kafka broker at {self.bootstrap_servers}")
            return True
            
        except KafkaError as e:
            # 捕获Kafka相关错误（如连接失败、配置错误等）
            logger.error(f"Failed to connect to Kafka broker: {e}")
            return False
            
    def send(self, data: Dict) -> bool:
        """
        Send cryptocurrency data to Kafka.
        发送加密货币数据到Kafka
        
        该方法会：
        1. 验证数据格式和生产者连接状态
        2. 根据加密货币符号创建主题名称
        3. 将数据发送到对应的Kafka主题
        4. 等待发送完成并处理结果
        
        Args:
            data: Dictionary containing cryptocurrency data
                 包含加密货币数据的字典
                 - 必须包含'symbol'字段（如'BTC', 'ETH'）
                 - 其他字段可以是价格、时间戳、交易量等
            
        Returns:
            bool: True if send successful, False otherwise
            bool: 发送成功返回True，失败返回False
        """
        # 检查生产者是否已连接
        if not self.producer:
            logger.error("Producer not connected")
            return False
            
        try:
            # Extract symbol and create topic name
            # 从数据中提取加密货币符号
            symbol = data.get('symbol', '').lower()  # 转换为小写以保持一致性
            if not symbol:
                logger.error("No symbol in data")
                return False
                
            # 构建Kafka主题名称：{前缀}.{符号}
            # 例如：crypto_prices.btc, crypto_prices.eth
            topic = f"{self.topic_prefix}.{symbol}"
            
            # Send data to Kafka
            # 发送数据到Kafka主题
            # key: 使用符号作为分区键，确保相同符号的数据进入同一分区
            # value: 发送完整的数据字典
            future = self.producer.send(
                topic=topic,
                key=symbol,
                value=data
            )
            
            # Wait for the send to complete
            # 等待发送操作完成，设置10秒超时
            # 这确保我们能够捕获发送过程中的任何错误
            future.get(timeout=10)
            logger.debug(f"Sent data to topic {topic}: {data}")
            return True
            
        except KafkaError as e:
            # 捕获Kafka相关错误（如主题不存在、网络问题等）
            logger.error(f"Failed to send data to Kafka: {e}")
            return False
            
        except Exception as e:
            # 捕获其他未预期的错误
            logger.error(f"Unexpected error sending data to Kafka: {e}")
            return False
            
    def close(self):
        """
        Close the Kafka producer.
        关闭Kafka生产者
        
        该方法会：
        1. 关闭生产者连接
        2. 释放相关资源
        3. 将producer实例设置为None
        
        注意：在程序结束时应该调用此方法以正确清理资源
        """
        if self.producer:
            self.producer.close()  # 关闭生产者连接
            logger.info("Kafka producer closed")
            self.producer = None  # 重置为None 
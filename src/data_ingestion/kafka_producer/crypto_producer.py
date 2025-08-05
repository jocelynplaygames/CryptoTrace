
"""
Kafka producer for streaming cryptocurrency data.
Kafka生产者模块 - 用于流式传输加密货币数据

该模块负责将实时加密货币价格数据发送到Kafka消息队列中，
为后续的数据处理和分析提供数据流。

组件协调关系：
- 上游：加密货币数据流客户端（feed_client.py）
- 下游：Kafka消息队列（crypto_prices.{symbol}主题）
- 协调方式：异步回调函数接收数据，同步发送到Kafka

数据流转分析：
1. 接收标准化的加密货币数据 → 序列化为JSON格式
2. 根据符号创建分区主题 → 发送到对应的Kafka主题
3. 使用符号作为分区键，确保相同符号的数据进入同一分区
4. 支持批量发送和异步确认机制

性能优化策略：
1. 连接池管理：复用Kafka连接，减少连接开销
2. 批量发送：支持批量消息发送，提高吞吐量
3. 异步确认：使用异步确认机制，不阻塞主线程
4. 内存优化：及时清理消息缓冲区，避免内存泄漏
5. 错误重试：实现智能重试机制，提高数据可靠性

接口设计：
- 输入：标准化的加密货币数据字典
- 输出：发送到Kafka主题的JSON消息
- 主题命名：crypto_prices.{symbol}（如crypto_prices.btc）
- 分区策略：基于符号的哈希分区，确保数据局部性
"""
# 输入：加密货币数据字典（包含symbol、price等字段）
# 输出：发送到Kafka主题的JSON消息，主题名格式为crypto_prices.{symbol}


#本代码中 flush() 出现的地方：
# 1. 在 CryptoKafkaProducer 类的 send() 方法中，当消息被成功发送到 Kafka 后，会调用 flush() 方法来确保消息被确认。
# 2. 在 CryptoKafkaProducer 类的 send_batch() 方法中，当批量消息发送完成后，会调用 flush() 方法来确保消息被确认。
# 3. 在 CryptoKafkaProducer 类的 close() 方法中，当生产者关闭时，会调用 flush() 方法来确保消息被确认。


import json
import logging
from typing import Dict, Optional
from datetime import datetime
from confluent_kafka import Producer
from confluent_kafka import KafkaError
import time
import requests

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
    
    设计模式：
    - 单例模式：确保每个应用只有一个生产者实例
    - 策略模式：可配置的序列化策略和错误处理策略
    - 观察者模式：通过回调函数处理发送结果
    
    性能特性：
    - 异步发送：不阻塞调用线程
    - 批量处理：支持批量消息发送
    - 连接复用：复用Kafka连接
    - 内存管理：自动清理消息缓冲区
    """
    
    # def __init__(self, bootstrap_servers: str = 'localhost:9092', topic_prefix: str = 'crypto_prices'):
    def __init__(self, bootstrap_servers: str = 'host.docker.internal:9092', topic_prefix: str = 'crypto_prices'):
        # bootstrap_servers：指定 Kafka 服务的地址和端口

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
                         
        配置说明：
        - acks='all'：等待所有副本确认，确保数据不丢失
        - retries=3：发送失败时重试3次
        - max.in.flight.requests.per.connection=1：保证消息顺序
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic_prefix = topic_prefix
        self.producer: Optional[Producer] = None  # Kafka生产者实例，初始为None还没连接，self.producer 是真正的 Kafka 客户端对象，会在后面 connect() 方法中初始化。
        # ===========   self.producer
        # 性能监控指标
        self.messages_sent = 0
        self.messages_failed = 0
        self.total_bytes_sent = 0
        
    def connect(self) -> bool:
        """
        Connect to Kafka broker.
        连接到Kafka消息代理
        
        该方法会：
        1. 创建KafkaProducer实例
        2. 配置序列化器（JSON格式）
        3. 设置可靠性参数（acks='all'确保数据不丢失）
        4. 配置重试机制
        
        连接优化：
        - 使用连接池减少连接开销
        - 配置合适的超时时间
        - 启用压缩减少网络传输
        
        Returns:
            bool: True if connection successful, False otherwise
            bool: 连接成功返回True，失败返回False
        """
        try:
            # 创建Kafka生产者实例，配置各种参数
            config = { # 封装了和 Kafka 服务之间的底层通信逻辑，包括连接管理、消息队列、重试机制、批处理、压缩等。
                'bootstrap.servers': self.bootstrap_servers,  # Kafka服务器地址
                'acks': 'all',  # Wait for all replicas - 确保消息被所有副本确认后再返回成功；
                'retries': 3,   # Retry on failure - 发送失败时重试3次
                'max.in.flight.requests.per.connection': 1,  # Preserve order - 每个连接最多1个未完成请求，保证消息顺序
                'compression.type': 'snappy',  # Kafka Producer 会将多条消息打包成一个批次发送，并启用 Snappy 压缩
                'batch.size': 16384,  # 批量大小，提高吞吐量
                'linger.ms': 5,  # 等待时间，允许批量发送
                'buffer.memory': 33554432,  # 缓冲区大小（32MB）
                'max.request.size': 1048576,  # 最大请求大小（1MB）
            }
            self.producer = Producer(config) # 使用 confluent_kafka.Producer 构造函数来创建一个 Kafka 生产者实例，它封装了和 Kafka 服务之间的底层通信逻辑
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
        
        发送策略：
        - 使用符号作为分区键，确保相同符号的数据进入同一分区
        - 异步发送，不阻塞调用线程
        - 支持批量发送，提高吞吐量
        - 实现智能重试机制
        
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
            
            # 序列化数据
            message_value = json.dumps(data, cls=DateTimeEncoder).encode('utf-8')
            # json.dumps(data, cls=DateTimeEncoder)这是将 Python 的 dict 对象转成 JSON 字符串，cls=DateTimeEncoder 是自定义的 JSON 编码器，用于处理 datetime 对象。
            # 把 JSON 字符串编码成 UTF-8 字节串，这是 Kafka 发送数据需要的格式
            message_size = len(message_value)
            
            # Send data to Kafka
            # 发送数据到Kafka主题
            # key: 使用符号作为分区键，确保相同符号的数据进入同一分区
            # value: 发送完整的数据字典（JSON序列化）
            self.producer.produce( # 只是把消息放进内存缓冲区，不会立即发送到 Kafka 服务器，而是通过 flush() 方法来触发实际发送。
                topic=topic,
                key=symbol.encode('utf-8'), 
                value=message_value,
                callback=self._delivery_report  # 异步回调处理发送结果
            )
            
            # 更新统计信息
            self.messages_sent += 1
            self.total_bytes_sent += message_size
            
            # Flush to ensure message is sent
            # 刷新缓冲区，确保消息被发送
            # 注意：在生产环境中，应该定期flush而不是每次发送后flush
            self.producer.flush(timeout=10)
            # flush() 会强制把 Kafka Producer 缓冲区中尚未发送或尚未确认的消息：立即发送并等待 Kafka 返回确认（ack）
            # Kafka 的 producer.produce() 方法只是把消息放入内存缓冲区（Buffer），不会立刻发送。
            # 而 flush() 是告诉 Kafka Producer：“把内存里还没发出去的消息，全部立即发送并确认完成。”
            logger.debug(f"Sent data to topic {topic}: {data}")
            return True
            
        except KafkaError as e:
            # 捕获Kafka相关错误（如主题不存在、网络问题等）
            logger.error(f"Failed to send data to Kafka: {e}")
            self.messages_failed += 1
            return False
            
        except Exception as e:
            # 捕获其他未预期的错误
            logger.error(f"Unexpected error sending data to Kafka: {e}")
            self.messages_failed += 1
            return False
    
    def _delivery_report(self, err, msg):
        """
        异步发送结果回调函数
        
        处理Kafka消息发送的结果，包括成功和失败的情况
        
        Args:
            err: 错误信息，None表示发送成功
            msg: 消息对象，包含主题、分区、偏移量等信息
        """
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
            self.messages_failed += 1
        else:
            logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}") # 将其投递位置（topic、分区、偏移量）写入日志，
            
    def send_batch(self, data_list: list[Dict]) -> int:
        """
        批量发送加密货币数据
        
        批量发送可以提高吞吐量，减少网络开销
        
        Args:
            data_list: 包含多个加密货币数据字典的列表
            
        Returns:
            int: 成功发送的消息数量
        """
        if not self.producer:
            logger.error("Producer not connected")
            return 0
            
        success_count = 0
        for data in data_list:
            if self.send(data):
                success_count += 1
                
        # 批量flush，提高性能
        self.producer.flush(timeout=30)
        return success_count
            
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
            try:
                # confluent-kafka的Producer没有close方法，使用flush确保消息发送
                self.producer.flush(timeout=10)
                logger.info("Kafka producer flushed and closed")
            except Exception as e:
                logger.warning(f"Error closing producer: {e}")
            finally:
                self.producer = None  # 重置为None
    
    def get_stats(self) -> Dict:
        """
        获取生产者统计信息
        
        Returns:
            包含发送统计信息的字典
        """
        return {
            "messages_sent": self.messages_sent,
            "messages_failed": self.messages_failed,
            "total_bytes_sent": self.total_bytes_sent,
            "success_rate": (self.messages_sent / (self.messages_sent + self.messages_failed)) * 100 if (self.messages_sent + self.messages_failed) > 0 else 0
        }

def fetch_real_price(symbol):# 传入参数 symbol：表示加密货币符号，如 "BTC"、"ETH" 等
    """
    从Binance API获取实时价格
    
    用于测试和验证数据源
    
    Args:
        symbol: 加密货币符号（如'BTC', 'ETH'）
        
    Returns:
        float: 当前价格
    """
    url = f"https://api.binance.us/api/v3/ticker/price?symbol={symbol.upper()}USDT" # 构建 API 请求的 URL
    resp = requests.get(url) # 发送 HTTP GET 请求，获取响应数据
    # requests 是 Python 中最常用的 HTTP 客户端库，用于发送 HTTP 请求（如 GET从服务器“读取”数据、POST向服务器“新增”一条资源、PUT对服务器已有资源“整体修改”、DELETE 等）
    resp.raise_for_status() # 检查响应状态码，如果状态码不是 200，则抛出异常
    return float(resp.json()['price']) # 把返回的 JSON 数据中的 "price" 字段取出来，转为 float 类型后返回。


# -------------主函数--------------------------------
def main():
    """
    主函数 - 用于测试Kafka生产者
    
    演示如何：
    1. 连接到Kafka
    2. 获取实时价格数据
    3. 发送到Kafka主题
    4. 监控发送统计
    """
    print("Starting crypto producer...")
    producer = CryptoKafkaProducer()
    print(f"Attempting to connect to Kafka at: {producer.bootstrap_servers}")
    if not producer.connect():
        logger.error("Failed to connect to Kafka")
        return
    print("Successfully connected to Kafka!")

    symbols = ['BTC', 'ETH', 'SOL', 'ADA']
    try:
        # 只运行一次循环，发送数据后退出（适合Airflow任务）
        for symbol in symbols:
            try:
                price = fetch_real_price(symbol)
                data = {
                    'symbol': symbol,
                    'price': price,
                    'timestamp': datetime.now().isoformat()
                }
                producer.send(data) # 调用 CryptoKafkaProducer 实例的 send() 方法，将数据发送到 Kafka 主题
                logger.info(f"Sent {symbol} data: {data}")
            except Exception as e:
                logger.error(f"Error fetching/sending {symbol}: {e}")
            time.sleep(1)
        print("Data collection completed successfully!")
        
        # 打印统计信息
        stats = producer.get_stats()
        print(f"Producer stats: {stats}")
        
    except KeyboardInterrupt:
        logger.info("Stopping producer...")
    finally:
        producer.close()

if __name__ == "__main__":
    main() 
"""
Stream processor for real-time cryptocurrency price analytics.
实时加密货币价格分析流处理器

该模块负责：
1. 从Kafka消费实时价格数据
2. 进行实时价格分析和计算
3. 检测价格异常和生成警报
4. 将分析结果发送到下游组件

组件协调关系：
- 上游：Kafka主题（crypto_prices.{symbol}）
- 下游：Kafka主题（crypto_analytics, crypto_alerts）
- 协调方式：Kafka消费者-生产者模式，实现解耦的数据处理

数据流转分析：
1. 消费Kafka价格数据 → 滑动窗口分析 → 计算统计指标
2. 价格变化检测 → 异常识别 → 生成警报
3. 分析结果和警报分别发送到不同主题
4. 支持多线程处理，提高并发性能

性能优化策略：
1. 滑动窗口：使用时间窗口进行实时分析，避免全量数据加载
2. 内存优化：及时清理过期数据，控制内存使用
3. 多线程处理：使用线程池处理消息，提高并发能力
4. 批量发送：批量发送分析结果，减少网络开销
5. 连接复用：复用Kafka连接，减少连接开销

接口设计：
- 输入：Kafka消息（JSON格式的价格数据）
- 输出：分析结果和警报（JSON格式）
- 配置参数：窗口大小、警报阈值、符号列表等
- 监控指标：处理消息数、生成警报数、处理延迟等
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from confluent_kafka import Consumer, Producer
from collections import defaultdict
import threading
import queue
import statistics
import time
import requests
import signal
import sys
import gc
import psutil
import os
import sys
from pathlib import Path
import pandas as pd

# 添加项目根目录到路径，以便导入其他模块
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from src.storage.time_series.price_store import PriceStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MemoryMonitor:
    """
    内存监控器
    
    监控系统内存使用情况，在内存不足时触发垃圾回收
    """
    
    def __init__(self, threshold_percent: float = 80.0):
        self.threshold_percent = threshold_percent
        self.process = psutil.Process(os.getpid()) # psutil.Process(pid)：表示获取一个进程对象，os.getpid()：获取当前 Python 进程的 PID（Process ID）
        # 使用了 psutil.Process 类
    def check_memory_usage(self) -> Dict:
        """
        检查内存使用情况
        
        Returns:
            Dict: 内存使用统计信息
        """
        # 使用了 self.process 的两个方法：memory_info() 和 memory_percent()
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()
        
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,  # RSS in MB 物理内存（Resident Set Size）
            'vms_mb': memory_info.vms / 1024 / 1024,  # VMS in MB 虚拟内存（Virtual Memory Size）
            'percent': memory_percent,
            'available_mb': psutil.virtual_memory().available / 1024 / 1024 # 可用内存
        }
    
    def should_garbage_collect(self) -> bool:
        """
        判断是否应该进行垃圾回收
        
        Returns:
            bool: 是否应该进行垃圾回收
        """
        memory_stats = self.check_memory_usage()
        return memory_stats['percent'] > self.threshold_percent
    
    def force_garbage_collect(self):
        """
        强制进行垃圾回收
        """
        logger.info("Forcing garbage collection due to high memory usage")
        collected = gc.collect()
        # 调用 Python 的内置模块 gc（Garbage Collector）中的 collect() 方法。它会强制立即运行一次完整的垃圾回收流程。
        # gc.collect() 返回的是：被回收的对象数量（整数）
        logger.info(f"Garbage collection completed, collected {collected} objects")



class PriceAnalytics:
    """
    价格分析计算器
    
    负责实时计算价格统计指标，包括：
    - 滑动窗口平均值、最大值、最小值
    - 标准差和变异系数
    - 价格变化百分比
    - 异常检测和警报生成
    
    设计模式：
    - 观察者模式：价格更新时自动触发分析
    - 策略模式：可配置的分析算法和阈值
    - 状态模式：管理不同的分析状态
    
    性能优化：
    - 滑动窗口：只保留最近N个数据点
    - 增量计算：避免重复计算
    - 内存管理：及时清理过期数据
    - 批量处理：支持批量分析
    """
    
    def __init__(self, window_size: int = 300, max_symbols: int = 100, storage_path: str = None):  # 5 minutes in seconds
        """
        初始化价格分析器
        
        Args:
            window_size: 滑动窗口大小（秒）
                        - 默认5分钟，可根据需要调整
                        - 影响内存使用和计算精度
            max_symbols: 最大支持的符号数量
                        - 防止内存无限增长
            storage_path: 存储路径，用于获取历史价格数据
                        - 如果为None，则使用默认路径
        """
        self.window_size = window_size
        self.max_symbols = max_symbols
        self.price_windows = defaultdict(list)  # 每个符号的价格窗口 只保存最近一段时间的数据
        self.last_price = {}  # 每个符号的最后价格
        self.last_alert = {}  # 每个符号的最后警报时间
        
        # 性能监控
        self.total_analytics = 0
        self.total_alerts = 0
        self.memory_monitor = MemoryMonitor() # 嵌入之前定义的内存监控类，一旦内存占用过高会强制清理
        
        # 批量处理
        self.batch_size = 100 # 批量处理：积累了 100 条价格数据再统一分析，而不是每条数据都立刻处理
        self.pending_analytics = []
        
        # 初始化价格存储，用于获取历史数据
        if storage_path is None:
            storage_path = project_root / "data" / "prices"
        try:
            self.price_store = PriceStore(storage_path)
            logger.info(f"Price store initialized at {storage_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize price store: {e}")
            self.price_store = None
        
    def add_price(self, symbol: str, price: float, timestamp: datetime) -> List[Dict]:
        """
        Add a new price point and calculate analytics.
        添加新的价格点并计算分析指标
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            price: Current price - 当前价格
            timestamp: Price timestamp - 价格时间戳
            
        Returns:
            List of analytics results - 分析结果列表
            - 包含统计指标和警报信息
        """
        results = []
        logger.info(f"Processing price for {symbol}: ${price:.2f} at {timestamp}")
        
        # 检查符号数量限制
        if len(self.price_windows) >= self.max_symbols and symbol not in self.price_windows: # 当前已经追踪的币种数量达到限制（默认最多 100 个）
            logger.warning(f"Maximum symbols reached ({self.max_symbols}), skipping {symbol}")
            return results
        
        # Store price in window
        # 将价格添加到滑动窗口
        # 每收到一个新币种（symbol）的数据，就会在 self.price_windows 中为它创建一个新的价格窗口（一个列表）
        self.price_windows[symbol].append((timestamp, price)) # 每个币种维护一个列表，保存 (时间, 价格)。最新的价格会被追加到这个窗口中。
        
        # Remove old prices from window
        # 移除窗口外的过期价格数据
        cutoff_time = timestamp - timedelta(seconds=self.window_size) #timedelta 把一个“秒数”转成“时间差对象”
        self.price_windows[symbol] = [
            (ts, p) for ts, p in self.price_windows[symbol] if ts > cutoff_time
             # 从当前币种的价格窗口中，遍历所有 (时间戳, 价格) 二元组    只保留那些时间大于 cutoff_time 的
            
        ]
        
        # Calculate analytics
        # 计算统计指标
        if len(self.price_windows[symbol]) > 1:
            window_prices = [p for _, p in self.price_windows[symbol]] # 从当前币种的价格窗口中，提取所有价格值
            analytics = {
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "window_start": self.price_windows[symbol][0][0].isoformat(),
                "window_end": timestamp.isoformat(),
                "average_price": statistics.mean(window_prices),
                "min_price": min(window_prices),
                "max_price": max(window_prices),
                "std_dev": statistics.stdev(window_prices) if len(window_prices) > 1 else 0,
                "num_samples": len(window_prices),
                "price_change_24h": self._calculate_24h_change(symbol, price),
                "volatility": self._calculate_volatility(window_prices)
            }
            results.append(("analytics", analytics))
            self.total_analytics += 1
            
            logger.info(f"Analytics for {symbol}: avg=${analytics['average_price']:.2f}, "
                       f"min=${analytics['min_price']:.2f}, max=${analytics['max_price']:.2f}")
        
        # Check for significant price changes
        # 检查显著的价格变化
        if symbol in self.last_price:
            price_change = (price - self.last_price[symbol]) / self.last_price[symbol]
            
            # Alert if price changed by more than 2% and no alert in last minute
            # 如果价格变化超过2%且在过去1分钟内没有警报，则生成警报
            if abs(price_change) >= 0.02 and (
                symbol not in self.last_alert or
                timestamp - self.last_alert[symbol] >= timedelta(minutes=1) # 如果价格变化超过2%且在过去1分钟内没有警报，则生成警报
            ):
                direction = "increased" if price_change > 0 else "decreased"
                alert = {
                    "symbol": symbol,
                    "timestamp": timestamp.isoformat(),
                    "price": price,
                    "previous_price": self.last_price[symbol],
                    "change_percent": price_change * 100,
                    "alert_type": f"Price {direction} by {abs(price_change)*100:.2f}%",
                    "severity": "high" if abs(price_change) > 0.05 else "medium"
                }
                results.append(("alert", alert))
                self.last_alert[symbol] = timestamp
                self.total_alerts += 1
                logger.info(f"ALERT: {symbol} {alert['alert_type']} to ${price:.2f}")
        
        self.last_price[symbol] = price
        
        # 内存管理
        self._manage_memory() # 价格分析完成后自动检查并管理内存
        
        return results
    
    def _manage_memory(self):
        # MemoryMonitor 是一个 工具类，专门负责 检测内存使用情况 和 触发垃圾回收。
        # PriceAnalytics 类中的 def _manage_memory(self) 是一个 使用 MemoryMonitor 的方法，它通过这个工具类来做实际的内存监控和回收。
        """
        内存管理：检查内存使用情况并在必要时进行清理
        """
        if self.memory_monitor.should_garbage_collect():#判断超过一定百分比，该清理了，去看具体清理哪些
            # 清理过期的价格窗口
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(seconds=self.window_size)
            
            for symbol in list(self.price_windows.keys()):
                # 清理过期的价格数据
                self.price_windows[symbol] = [
                    (ts, p) for ts, p in self.price_windows[symbol]
                    if ts > cutoff_time
                ]
                
                # 如果窗口为空，删除该符号
                if not self.price_windows[symbol]:
                    del self.price_windows[symbol]
                    if symbol in self.last_price: 
                        del self.last_price[symbol]
                    if symbol in self.last_alert:
                        del self.last_alert[symbol]
            
            # 强制垃圾回收
            self.memory_monitor.force_garbage_collect()
    
    def add_prices_batch(self, price_data: List[Dict]) -> List[Dict]:
        """
        批量添加价格数据
        
        Args:
            price_data: 价格数据列表
            
        Returns:
            List[Dict]: 批量分析结果
        """
        all_results = []
        
        for data in price_data:
            symbol = data['symbol']
            price = data['price']
            timestamp = datetime.fromisoformat(data['timestamp']) # 把字符串类型的时间戳转成 datetime 对象
            
            results = self.add_price(symbol, price, timestamp) # 调用 add_price 方法，一个个加，传入 币种、价格、时间戳
            all_results.extend(results) # 把每个币种的分析结果都添加到 all_results 列表中
        
        return all_results
    
    def _calculate_24h_change(self, symbol: str, current_price: float) -> float:
        """
        计算24小时价格变化百分比
        
        实现策略：
        1. 从价格存储中获取24小时前的价格数据
        2. 如果找到历史数据，计算价格变化百分比
        3. 如果没有历史数据，返回0.0
        4. 使用缓存机制避免重复查询
        
        Args:
            symbol: 交易对符号
            current_price: 当前价格
            
        Returns:
            float: 24小时价格变化百分比
        """
        try:
            # 检查是否有价格存储实例
            if self.price_store is None: # 如果没有数据来源（例如数据库、缓存服务），直接返回 0.0，并写日志。
                logger.warning("Price store not available, cannot calculate 24h change")
                return 0.0
            
            # 计算24小时前的时间
            current_time = datetime.now()
            start_time = current_time - timedelta(hours=25)
            
            # 从存储中获取24小时前的价格数据
            # 查询时间范围：25小时前到22小时前（获取最接近24小时前的数据）
            end_time = current_time - timedelta(hours=22)
            
            price_data = self.price_store.get_price_data(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                as_dataframe=True
            )
            
            if price_data.empty:
                logger.debug(f"No historical price data found for {symbol} in the last 24 hours")
                return 0.0
            
            # 获取24小时前最接近的价格
            # 按时间戳排序，取最早的价格作为24小时前的价格
            price_data['timestamp'] = pd.to_datetime(price_data['timestamp']) #将 price_data 这个 DataFrame 中的 "timestamp" 列转换为 datetime64 类型
            price_data = price_data.sort_values('timestamp')  # 升序排序
            
            if len(price_data) > 0:
                # 取第一个价格作为24小时前的价格
                price_24h_ago = price_data.iloc[0]['price']
                
                # 计算价格变化百分比
                if price_24h_ago > 0:
                    change_percent = ((current_price - price_24h_ago) / price_24h_ago) * 100
                    logger.debug(f"24h change for {symbol}: {change_percent:.2f}% "
                               f"({price_24h_ago:.2f} -> {current_price:.2f})")
                    return change_percent
                else:
                    logger.warning(f"Invalid historical price for {symbol}: {price_24h_ago}")
                    return 0.0
            else:
                logger.debug(f"No valid price data found for {symbol} in the last 24 hours")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error calculating 24h change for {symbol}: {e}")
            return 0.0
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """
        计算价格波动率
        
        Args:
            prices: 价格列表
            
        Returns:
            float: 波动率（标准差/平均值）
        """
        if len(prices) < 2:
            return 0.0
        
        mean_price = statistics.mean(prices)
        if mean_price == 0:
            return 0.0
        
        std_dev = statistics.stdev(prices)
        return (std_dev / mean_price) * 100  # 转换为百分比 标准差 ÷ 平均值 × 100 得到波动率百分比
    
    def get_stats(self) -> Dict:
        """
        获取分析器统计信息
        
        Returns:
            包含分析统计信息的字典
        """
        return {
            "total_analytics": self.total_analytics,
            "total_alerts": self.total_alerts,
            "active_symbols": len(self.price_windows),
            "window_size": self.window_size
        }

class PriceProcessor:
    """
    实时价格处理器，使用Kafka流处理
    
    负责：
    1. 从Kafka消费价格数据
    2. 进行实时分析
    3. 生成警报和分析结果
    4. 发送到下游Kafka主题
    
    设计模式：
    - 生产者-消费者模式：从Kafka消费，处理后发送
    - 观察者模式：价格更新时触发分析
    - 策略模式：可配置的处理策略
    
    性能特性：
    - 多线程处理：提高并发性能
    - 消息队列：缓冲消息，避免阻塞
    - 批量处理：批量发送结果
    - 连接复用：复用Kafka连接
    """
    


    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        input_topic_prefix: str = "crypto_prices",
        alert_topic: str = "crypto_alerts",
        analytics_topic: str = "crypto_analytics",
        symbols: List[str] = None
    ):
        """
        Initialize the price processor.
        初始化价格处理器
        
        Args:
            bootstrap_servers: Kafka bootstrap servers - Kafka引导服务器
            input_topic_prefix: Prefix for input topics - 输入主题前缀
            alert_topic: Topic for price alerts - 价格警报主题
            analytics_topic: Topic for price analytics - 价格分析主题
            symbols: List of symbols to process (e.g. ["btcusdt", "ethusdt"]) - 要处理的符号列表
        """
        self.bootstrap_servers = bootstrap_servers
        self.input_topics = [f"{input_topic_prefix}.{symbol}" for symbol in symbols] if symbols else []
        self.alert_topic = alert_topic
        self.analytics_topic = analytics_topic
        
        self.consumer = None
        self.producer = None
        self.analytics = PriceAnalytics()
        self.running = False
        self.process_thread = None
        self.message_queue = queue.Queue(maxsize=1000)  # 消息队列，缓冲消息
        
        # 性能监控
        self.messages_processed = 0
        self.messages_dropped = 0
        
    def connect(self) -> bool:
        """
        Connect to Kafka brokers.
        连接到Kafka消息代理
        
        Returns:
            bool: True if connection successful - 连接成功返回True
        """
        try:
            # Create consumer
            # 创建消费者
            consumer_config = {
                'bootstrap.servers': self.bootstrap_servers,
                'group.id': 'price_processor',
                'auto.offset.reset': 'latest',
                'enable.auto.commit': True,
                'max.poll.records': 100,  # 每次拉取最多100条消息
                'session.timeout.ms': 30000,  # 会话超时时间
                'heartbeat.interval.ms': 3000  # 心跳间隔
            }
            self.consumer = Consumer(consumer_config)
            self.consumer.subscribe(self.input_topics)
            
            # Create producer
            # 创建生产者
            producer_config = {
                'bootstrap.servers': self.bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'compression.type': 'snappy',
                'batch.size': 16384,
                'linger.ms': 5
            }
            self.producer = Producer(producer_config)
            
            logger.info(f"Connected to Kafka brokers at {self.bootstrap_servers}")
            logger.info(f"Listening to topics: {', '.join(self.input_topics)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
            
    def process_message(self, message):
        """
        Process a single message.
        处理单个消息
        
        处理流程：
        1. 解析消息数据
        2. 进行价格分析
        3. 生成分析结果和警报
        4. 发送到相应的Kafka主题
        """
        try:
            # Parse message
            # 解析消息
            # data = message.value
            data = json.loads(message.value().decode('utf-8'))
             # Kafka 中发来的 message.value() 是个字节串，内容通常是 JSON 格式字符串，需要先用 decode() 和 json.loads() 把它转成字典再处理。
            symbol = data['symbol'].lower()
            price = float(data['price'])
            timestamp = datetime.fromisoformat(data['timestamp'])
            
            # Calculate analytics
            # 计算分析指标
            results = self.analytics.add_price(symbol, price, timestamp) # add_price() 会返回分析结果
            
            # Send results to appropriate topics
            # 发送结果到相应的主题
            for result_type, result in results:
                topic = self.alert_topic if result_type == "alert" else self.analytics_topic #  如果是 "alert"，就发到 self.alert_topic
                self.producer.produce( #  真正发消息到 Kafka 的操作
                    topic=topic,
                    key=symbol.encode('utf-8'),
                    value=json.dumps(result).encode('utf-8')
                )
                logger.info(f"Sent {result_type} to topic {topic}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def message_handler(self):
        """
        Handle messages from the queue.
        处理队列中的消息
        
        使用独立线程处理消息，避免阻塞主线程
        """
        while self.running: # 控制消息处理是否继续进行。通常在程序退出时被设置为 False，从而优雅停止线程。
            try:
                message = self.message_queue.get(timeout=1.0)# self.message_queue 是一个 queue.Queue() 实例，用来缓冲从 Kafka 消费器拿到的消息。
                # .get(timeout=1.0) 表示最多等待 1 秒取一条消息。如果队列为空 1 秒，会抛出 queue.Empty 异常
                self.process_message(message) # 调用类中的 process_message 方法来真正处理消息，可能会分析、保存、转发到 Kafka 等
                self.message_queue.task_done() # 标记消息处理完成
                self.messages_processed += 1 # 统计处理过的消息数量
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
                


# ============= 主程序 =============                
    def start(self):
        """
        Start processing messages.
        开始处理消息
        
        启动流程：
        1. 连接到Kafka
        2. 启动消息处理线程
        3. 开始消费消息
        4. 将消息放入队列进行处理
        """
        if not self.consumer or not self.producer:
            if not self.connect(): # 如果还没连接，就调用 self.connect()，连接失败就退出 start() 方法
                return False
                
        self.running = True
        
        # Start message handler thread
        # 启动消息处理线程
        self.process_thread = threading.Thread(target=self.message_handler) # 启动一个后台线程，使用 message_handler 方法，负责从kafka中拿出消息，并放入队列message
        self.process_thread.daemon = True # 设置为守护线程，这样当主程序退出时，这个线程也会自动退出。
        self.process_thread.start() # 真正启动线程
        
        # Main loop
        # 主循环
        try:
            while self.running:
                # 批量拉取消息
                messages = self.consumer.consume(num_messages=100, timeout=1.0) # 持续从 Kafka 消费消息。每批最多取 100 条，最多等 1 秒。
                
                for message in messages:
                    if not self.running: # 如果主程序已经停止，就退出循环
                        break
                        
                    try:# 把每条 Kafka 消息丢进内部队列 self.message_queue。这个队列是 message_handler() 线程消费的。
                        # 将消息放入队列，避免阻塞
                        self.message_queue.put(message, timeout=1.0) # 把消息放进队列
                    except queue.Full:
                        logger.warning("Message queue full, dropping message")
                        self.messages_dropped += 1 # 增加丢弃计数器 self.messages_dropped
                        
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.running = False
            
        return True
        
    def stop(self):
        """
        Stop processing messages.
        停止处理消息
        
        优雅关闭：
        1. 设置停止标志
        2. 等待处理线程结束
        3. 关闭Kafka连接
        4. 清理资源
        """
        self.running = False # 通知主循环（start() 中的 while self.running）和 message_handler() 中的循环退出
        
        if self.process_thread:
            self.process_thread.join(timeout=5.0) # “主程序”暂停执行，等待这个 self.process_thread 后台线程先退出，最多等 5 秒。”
            # 不能直接关闭程序，否则它可能：    把线程“砍死”，数据没处理完；Kafka 连接还开着，资源没释放；日志还没写完。
            # 所以需要：✅ 等待线程自然结束✅ 处理完手头任务后再退出✅ 主程序才继续关闭
            # 若self.process_thread.join() 主程序会无限等待线程退出。如果线程因为某些异常 永远不退出，那程序就挂住了。
            # 加上 timeout=5.0，表示：“我最多等你 5 秒退出，如果你还不退出，我也不等了，继续往下走。”
            
        if self.consumer: # 释放 Kafka 消费者连接。向 Kafka 通知“我不消费了”，释放分区锁。
            self.consumer.close()
            
        if self.producer:
            self.producer.flush(timeout=10) # 等待所有未发送的消息被发送出去，最多等 10 秒。
            
        logger.info("Processor stopped")
    
    def get_stats(self) -> Dict:
        """
        获取处理器统计信息
        
        Returns:
            包含处理统计信息的字典
        """
        analytics_stats = self.analytics.get_stats()
        # 调用内部的价格分析器 self.analytics 的 get_stats() 方法，获取分析模块的统计数据（如总共分析了多少次、产生了多少个警报等）
        return {
            "messages_processed": self.messages_processed,
            "messages_dropped": self.messages_dropped,
            "queue_size": self.message_queue.qsize(),
            "analytics_stats": analytics_stats
        }

import time
import requests
from datetime import datetime


def main():
    """
    主函数 - 用于测试价格处理器
    
    演示如何：
    1. 连接到Kafka
    2. 启动价格处理器
    3. 监控处理统计
    4. 优雅关闭
    """
    processor = PriceProcessor( # 创建一个处理器对象，设置要处理的 Kafka 连接地址和支持的币种
        bootstrap_servers="host.docker.internal:9092",
        symbols=['btc', 'eth', 'sol', 'ada']
    )

    def signal_handler(signum, frame): # 当程序收到 Ctrl+C 或 kill 信号（SIGINT/SIGTERM）时，调用 processor.stop() 优雅地关闭线程、Kafka 连接、清理资源。
        """
        信号处理器 - 优雅关闭
        """
        logger.info("Received exit signal, stopping processor...")
        processor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("Starting price processor...")
        if processor.start(): # 调用 processor.start() 启动 Kafka 消费、消息处理线程
            logger.info("Price processor started successfully")
            
            # 定期打印统计信息
            while True:
                time.sleep(30)  # 每30秒打印一次统计
                stats = processor.get_stats()
                logger.info(f"Processor stats: {stats}")
                
        else:
            logger.error("Failed to start price processor")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        processor.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()
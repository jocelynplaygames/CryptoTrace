"""
WebSocket client for real-time cryptocurrency data feeds.
实时加密货币数据流WebSocket客户端

这个文件负责：
1. 连接到加密货币交易所的WebSocket API
2. 订阅实时价格数据流
3. 接收、验证和清理原始数据
4. 通过回调函数将处理后的数据传递给下游组件

组件协调关系：
- 上游：Binance WebSocket API（数据源）
- 下游：Kafka生产者（crypto_producer.py）
- 协调方式：异步回调函数机制，实现松耦合的数据传递

数据流转分析：
1. WebSocket连接建立 → 订阅指定交易对 → 接收实时数据流
2. 数据验证和清理 → 格式标准化 → 通过回调传递给Kafka生产者
3. 错误处理和重连机制确保数据流的连续性

性能优化策略：
1. 异步I/O：使用asyncio实现非阻塞的WebSocket通信
2. 指数退避重连：避免频繁重连对服务器造成压力
3. 内存优化：及时清理无效数据，避免内存泄漏
4. 连接池管理：复用WebSocket连接，减少连接开销
"""
import asyncio
import json
import logging
import websockets
from typing import Dict, List, Optional, Callable
from datetime import datetime
from websockets.exceptions import ConnectionClosed, WebSocketException
import time
import aiohttp

logging.basicConfig(level=logging.INFO) # 所有日志等级 ≥ INFO 的日志会被输出；
logger = logging.getLogger(__name__) # 创建一个与当前模块绑定的日志记录器。__name__ 是当前模块名（比如 'main' 或 'my_module'），这样每个模块都可以有自己独立的 logger。

class CryptoFeedClient:
    """
    加密货币数据流客户端
    
    负责从Binance等交易所获取实时加密货币价格数据，
    通过WebSocket连接实现低延迟的数据传输。
    
    设计模式：
    - 观察者模式：通过回调函数通知下游组件
    - 状态机模式：管理连接状态（连接中、已连接、断开、重连）
    - 策略模式：可配置的重连策略和错误处理策略
    """
    
    def __init__(self, symbols: List[str], on_message_callback: Optional[Callable] = None):# 调用方（例如主程序或另一个模块）创建 CryptoFeedClient 实例时注入的
        # 回调函数（Callback Function）是指：你把一个函数当成参数，传给另一个函数或对象，等到未来某个时刻再“调用”它。
        # CryptoFeedClient 并不自己决定怎么处理数据，而是允许“用户”传入一个函数来处理清洗后的行情数据。
        """
        Initialize the crypto feed client.
        初始化加密货币数据流客户端
        
        Args:
            symbols: List of cryptocurrency symbols to monitor (e.g., ["BTCUSDT", "ETHUSDT"])
                    要监控的加密货币符号列表
            on_message_callback: Optional callback function to handle received messages
                                处理接收消息的可选回调函数
                                
        性能考虑：
        - 符号列表大小影响内存使用和网络带宽
        - 回调函数应该是异步的，避免阻塞主线程
        """
        # Convert symbols to Binance format (e.g., BTC-USD -> BTCUSDT)
        # 将符号转换为Binance格式（例如：BTC-USD -> BTCUSDT）
        self.symbols = [s.replace("-", "").replace("USD", "USDT").lower() for s in symbols]
        self.on_message_callback = on_message_callback  # 数据回调函数，用于传递给下游
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        # self.websocket 是和 Binance 的 WebSocket 服务器之间建立好的那条“网络通道”，是 websockets.WebSocketClientProtocol 类型的对象，提供一系列方法，用它 .send(...) 可以发消息，.recv() 可以收消息。
    #self.websocket的生命周期： 在 connect() 中创建，在 _connection_loop() 中使用，在 close() 中关闭。
#connect() 启动
# 调用 _connection_loop()
# _connection_loop() 中连接 WebSocket
# 使用 websockets.connect(uri) 成功后，赋值给 self.websocket
# 连接建立后，该对象被多个方法共享使用：
# _subscribe() 发送订阅消息 → .send(...)
# _handle_messages() 接收数据 → .recv()
# close() 优雅关闭连接 → .close()

        self.is_connected = False
        self.reconnect_delay = 1  # Initial reconnect delay in seconds - 初始重连延迟（秒）
        self.max_reconnect_delay = 60  # Maximum reconnect delay in seconds - 最大重连延迟（秒）
        self._stop = False  # 停止标志
        self._connection_task = None  # 连接任务
        
        # 性能监控指标
        self.messages_received = 0
        self.messages_processed = 0
        self.connection_attempts = 0

    async def connect(self, uri: str = "wss://stream.binance.us:9443/ws"): #uri: Binance WebSocket 服务地址
        """
        Establish WebSocket connection with retry mechanism.
        建立WebSocket连接，带重试机制
        
        Args:
            uri: WebSocket endpoint URI - WebSocket端点URI
            
        连接策略：
        - 使用异步连接，不阻塞主线程
        - 实现自动重连机制，确保服务连续性
        - 支持优雅关闭，避免数据丢失
        """
        self._stop = False
        self._connection_task = asyncio.create_task(self._connection_loop(uri))
        await self._connection_task #当 connect() 被调用时，它不会立即返回，而是等 _connection_loop()（内部会自动重连）终止后才会结束。
# 如果你直接 await self._connection_loop()：会同步地运行 _connection_loop()，直到整个生命周期结束，不能动态管理任务（如取消）。
# 使用 create_task()可以：后续取消（cancel()），并发运行。挂起：asyncio 的事件循环继续调度其他协程，一旦 _connection_task 完成，这个 await 会恢复运行


# connect() 是外部调用的入口，
# _connection_loop() 是内部的核心循环；connect() 会创建一个异步任务，运行 _connection_loop()；
# 然后自己 await 挂起，等待 _connection_loop() 整个生命周期结束

    async def _connection_loop(self, uri: str):
        """
        Internal connection loop with retry mechanism.
        内部连接循环，带重试机制
        
        实现自动重连和错误恢复，确保数据流的连续性
        
        重连策略：
        - 指数退避：避免频繁重连对服务器造成压力
        - 最大重连延迟：防止无限等待
        - 优雅关闭：支持程序退出时的清理
        """
        while not self._stop:
            try: # 为了保证系统 不崩溃 并能 自动恢复，就需要把这些“危险代码”包在 try 里，然后在出错后优雅地处理
                # 连接建立
                async with websockets.connect(uri) as websocket:
                # websockets.connect(uri): 是 websockets 库提供的一个 异步函数；
                # 会尝试连接到 Binance 提供的 WebSocket 地址； 返回一个 WebSocket 连接对象（websockets.WebSocketClientProtocol 实例）；
                
                # async with ... as websocket
                # 是 异步上下文管理器；
                # 会自动管理连接的生命周期：
                # 连接成功后，赋值给 self.websocket；
                # 连接断开后，自动关闭连接；
                # 连接成功后，赋值给 self.websocket；
                    self.websocket = websocket #  这一行把建立好的 WebSocket 连接对象赋值给了 self.websocket，这个对象后续就可以被整个类方法共享使用了。
                    self.is_connected = True
                    self.connection_attempts += 1
                    logger.info(f"Connected to WebSocket feed (attempt {self.connection_attempts})")
                    
                    # Subscribe to specified symbols
                    # 订阅指定的符号
                    # 向 Binance WebSocket 发送订阅请求，告诉服务器你想监听哪些交易对（symbols）
                    await self._subscribe()
                    
                    # Reset reconnect delay on successful connection
                    # 成功连接后重置重连延迟
                    # 指数退避（exponential backoff）重连机制的一部分。如果上一次连接失败，程序会逐渐增加等待时间（1 秒、2 秒、4 秒……）。
                    self.reconnect_delay = 1
                    
                    # Start message handling
                    # 开始消息处理
                    # 接收每条 WebSocket 消息
                    # 使用 _validate_and_clean_data() 清洗、验证数据结构
                    # 调用用户提供的 on_message_callback() 把处理后的数据发给下游（如 Kafka）
                    await self._handle_messages()
                    
            except (ConnectionClosed, WebSocketException) as e:
                # ConnectionClosed: WebSocket 连接被服务器或客户端关闭
                # WebSocketException: WebSocket 通信中出现的通用异常

                #判断是否“被用户手动关闭”
                # 如果你调用了 await client.close()，会设置 self._stop = True
                if self._stop:
                    break
                logger.error(f"WebSocket connection error: {e}")
                # 触发重连逻辑
                # 使用“指数退避”的方式等待一段时间再尝试重新连接；
                # 重连前还会执行一次网络健康检查（ping Binance API）；
                await self._handle_reconnection()
                
            except Exception as e:
                if self._stop:
                    break
                logger.error(f"Unexpected error: {e}")
                await self._handle_reconnection()
            
            finally: # 无论连接成功与否，都清理连接状态
                self.is_connected = False
                self.websocket = None



# 以下是具体功能的实现


    async def _subscribe(self): # 是一个异步方法，必须用 await 调用
        """
        Send subscription message for specified symbols.
        发送指定符号的订阅消息
        
        向交易所发送订阅请求，开始接收实时数据流
        
        订阅策略：
        - 批量订阅：一次性订阅所有符号，减少网络开销
        - 错误处理：订阅失败时记录日志但不中断连接
        - 重试机制：连接断开后自动重新订阅
        """
        if not self.websocket or not self.is_connected: #如果当前还没有连接（或者连接被意外断开了）
            return
            
        # Create subscription message for each symbol
        # 为每个符号创建订阅消息
        streams = [f"{symbol}@ticker" for symbol in self.symbols] #@ticker 是 Binance 提供的实时价格/交易量快照流
        subscription_message = { # 发送如下 JSON 消息告诉 Binance：“我要订阅这些币种的 ticker 行情数据”：
            "method": "SUBSCRIBE",
            "params": streams, # ["btcusdt@ticker", "ethusdt@ticker"],
            "id": 1
        }
        
        try:
            await self.websocket.send(json.dumps(subscription_message)) #发送如下 JSON 消息
            logger.info(f"Subscribed to symbols: {self.symbols}")
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")

    async def _handle_messages(self):
        """
        Handle incoming WebSocket messages.
        处理传入的WebSocket消息
        
        这是数据接收的核心循环，负责：
        1. 接收原始WebSocket消息
        2. 解析JSON数据
        3. 验证和清理数据
        4. 通过回调函数传递给下游
        
        性能优化：
        - 异步消息处理：不阻塞接收循环
        - 批量处理：可以考虑批量发送到下游
        - 内存管理：及时清理无效数据
        - 错误隔离：单个消息错误不影响整体处理
        """
        if not self.websocket or not self.is_connected:
            return
            
        # 添加消息处理统计
        message_count = 0
        error_count = 0
        last_stats_time = time.time() # Python 标准库 time 模块中的函数，返回的是当前时间的Unix 时间戳（即从1970年到现在的秒数，浮点型）：
        
        try:
            async for message in self.websocket: #异步迭代器，每当 Binance WebSocket 发来一条新消息，就触发一次 async for 循环体。
            # self.websocket 是 websockets.WebSocketClientProtocol 实例
            # 它实现了异步迭代协议（__aiter__() 和 __anext__()）
            # 所以你可以使用 async for 持续监听它的新消息
                if self._stop:# 程序手动调用 await client.close() 时，设置了 self._stop = True，这个逻辑会优雅退出消息接收循环。
                    break
                    
                self.messages_received += 1
                message_count += 1
                
                try:
                    data = json.loads(message) # 字符串格式的消息转换为 Python 字典。如果失败会被捕获到 except json.JSONDecodeError
                    
                    # Skip subscription responses
                    # 跳过订阅响应
                    if "result" in data: # Binance 在你订阅成功后，会发回一条“确认消息”
                        continue
                    
                    # Validate and clean the data
                    # 验证和清理数据
                    cleaned_data = self._validate_and_clean_data(data) # 调用类内方法，过滤无效值、统一字段结构（如 price、symbol、timestamp 等）。
                    
                    if cleaned_data and self.on_message_callback:
                        # 通过回调函数将清理后的数据传递给下游
                        await self.on_message_callback(cleaned_data)
                        self.messages_processed += 1
                        
                except json.JSONDecodeError as e:
                    error_count += 1
                    logger.error(f"Failed to decode message: {e}")
                    # 添加错误率监控
                    if error_count > 100 and (error_count / message_count) > 0.1:
                        logger.warning(f"High error rate detected: {error_count/message_count:.2%}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing message: {e}")
                    # 添加错误恢复机制
                    if error_count > 50:
                        logger.warning("Too many errors, considering reconnection")
                        break
                
                # 定期打印统计信息
                current_time = time.time()
                if current_time - last_stats_time > 60:  # 每分钟打印一次统计
                    logger.info(f"Message processing stats: received={message_count}, "
                              f"processed={self.messages_processed}, errors={error_count}")
                    message_count = 0
                    error_count = 0
                    last_stats_time = current_time
                
        except Exception as e:
            if not self._stop:
                logger.error(f"Error in message handling loop: {e}")
                raise

    async def _handle_reconnection(self):
        """
        Handle reconnection with exponential backoff.
        处理重连，使用指数退避策略
        
        实现智能重连机制，避免频繁重连对服务器造成压力
        
        重连策略：
        - 指数退避：延迟时间逐渐增加
        - 最大延迟限制：防止无限等待
        - 优雅关闭支持：程序退出时立即停止重连
        - 健康检查：重连前检查网络状态
        """
        if self._stop:
            return
            
        self.is_connected = False # 重连前，先设置连接状态为 False
        
        # 添加网络健康检查
        if not await self._check_network_health():
            logger.warning("Network health check failed, will retry")
            
        logger.info(f"Attempting to reconnect in {self.reconnect_delay} seconds...")
        await asyncio.sleep(self.reconnect_delay)
        
        # Implement exponential backoff
        # 实现指数退避 每次重连失败，下一次的等待时间翻倍
        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def _check_network_health(self) -> bool:
        """
        检查网络健康状态
        
        Returns:
            bool: 网络是否健康
        """
        try:
            # 简单的网络连通性检查
            # 用 async with 包着 ClientSession()？
            # 因为这个 session 本质上会打开底层的 TCP 连接池和资源。你必须关闭它，否则会造成资源泄漏。
            # aiohttp.ClientSession() 是 aiohttp 提供的一个异步 HTTP 客户端会话对象（session object），用于管理你发起的 HTTP 请求。
            async with aiohttp.ClientSession() as session: #async with 表达式 as 变量:：1️⃣ 执行表达式2️⃣ 赋值给变量# 创建异步 HTTP 会话（aiohttp.ClientSession()）
            # session 是一个 HTTP 客户端会话对象
            # 类型是：aiohttp.ClientSession
            # 你可以用它发送各种请求：.get(), .post(), .put(), .delete() 等。

            #response 是一个 HTTP 响应对象
            # 类型是：aiohttp.ClientResponse
            # 这是对 GET 请求的响应封装，包含：# 响应状态码（response.status）、响应头（response.headers）、响应体（response.text）、响应时间（response.elapsed）、响应内容（response.content）

                async with session.get('https://api.binance.us/api/v3/ping', timeout=5) as response:
                    return response.status == 200 # 成功并且返回 200 状态码，说明网络通畅
        except Exception as e:
            logger.debug(f"Network health check failed: {e}")
            return False

    def _validate_and_clean_data(self, data: Dict) -> Optional[Dict]: # 来自 WebSocket 返回的 JSON 数据
        """
        Validate and clean received data.
        验证和清理接收到的数据
        
        将交易所的原始数据格式转换为标准化的内部格式，
        确保数据质量和一致性。
        
        数据质量保证：
        - 字段完整性检查：确保必需字段存在
        - 数据类型验证：确保数值字段为有效数字
        - 时间戳标准化：统一时间格式
        - 异常值过滤：过滤明显错误的数据
        - 数据范围检查：验证价格和交易量的合理性
        
        Args:
            data: Raw data received from WebSocket - 从WebSocket接收的原始数据
            
        Returns:
            Cleaned data dictionary or None if validation fails
            清理后的数据字典，验证失败时返回None
        """
        try:
            # Extract and validate required fields
            # 提取和验证必需字段
            required_fields = ["s", "c", "E"]  # symbol, current price, event time
            if not all(field in data for field in required_fields): # 必须字段都要存在，否则直接丢弃。
                logger.debug(f"Missing required fields in data: {data}")
                return None

            # Clean and format the data
            # 清理和格式化数据
            symbol = data["s"] # 交易对名称
            price = float(data["c"]) # 当前价格
            timestamp = datetime.fromtimestamp(data["E"] / 1000) # 事件时间
            #Binance 的时间戳字段 "E" 是以 毫秒（ms）为单位的整数，比如 1722423365000
            # Python 的 datetime.fromtimestamp() 需要的是 秒级时间戳（float/int）
            # 然后 datetime.fromtimestamp() 会自动转换为 2024-07-30 10:16:05 这样的日期时间对象

            volume_24h = float(data.get("v", 0)) # 24小时交易量 # 如果没有 "v" 字段，默认设为 0（防止 KeyError）
            
            # 数据质量检查
            if price <= 0:
                logger.warning(f"Invalid price for {symbol}: {price}")
                return None
                
            if volume_24h < 0:
                logger.warning(f"Invalid volume for {symbol}: {volume_24h}")
                volume_24h = 0
                
            # 检查时间戳的合理性
            current_time = datetime.now()
            if abs((current_time - timestamp).total_seconds()) > 3600:  # 1小时
                logger.warning(f"Suspicious timestamp for {symbol}: {timestamp}")
                return None
                
            # 检查价格变化的合理性（如果可能
            if hasattr(self, 'last_price') and symbol in self.last_price:
                #当前类 self 有属性 last_price（即 hasattr 为真）
                # 并且当前的 symbol（如 BTCUSDT）在 last_price 字典中
                last_price = self.last_price[symbol] # 取出上一次的价格
                price_change = abs(price - last_price) / last_price
                if price_change > 0.5:  # 50%的价格变化
                    logger.warning(f"Large price change for {symbol}: {price_change:.2%}")
                    # 不直接拒绝，但记录警告

            cleaned_data = {
                "symbol": symbol,
                "price": price,
                "timestamp": timestamp,
                "volume_24h": volume_24h,
                "sequence": int(data.get("E", 0))
            }

            return cleaned_data

        except (ValueError, KeyError) as e:
            logger.error(f"Error validating data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in data validation: {e}")
            return None

    async def close(self):
        """
        Close the WebSocket connection.
        关闭WebSocket连接
        
        优雅地关闭连接，清理资源，确保没有数据丢失
        
        清理步骤：
        1. 设置停止标志
        2. 关闭WebSocket连接
        3. 取消异步任务
        4. 清理资源引用
        """
        self._stop = True
        
        if self.websocket and self.is_connected: # 如果 websocket 对象存在，且还在连接中
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket connection: {e}")
            

# _connection_task	是后台运行的 async 任务控制句柄， _connection_loop()	是实际的 WebSocket 工作循环。
# 不会自动结束，除非满足以下两个条件之一：✅ 手动设置 self._stop = True	会跳出 while not self._stop 循环；✅ WebSocket 长时间异常、退出逻辑主动抛错	最终导致 _connection_loop() return 或 raise
        if self._connection_task:
            try:
                self._connection_task.cancel() # _connection_task 是 connect() 创建的后台协程任务
                await asyncio.gather(self._connection_task, return_exceptions=True) # 通过 asyncio.gather(..., return_exceptions=True) 处理取消带来的异常
            except Exception as e:
                logger.error(f"Error cancelling connection task: {e}")
            
        self.websocket = None
        self.is_connected = False
        logger.info("WebSocket connection closed")
        
    def get_stats(self) -> Dict: # 预留的监控入口，打印状态
        """
        获取性能统计信息
        
        Returns:
            包含连接状态、消息处理统计等信息的字典
        """
        return {
            "is_connected": self.is_connected,
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
            "connection_attempts": self.connection_attempts,
            "reconnect_delay": self.reconnect_delay
        } 
"""
WebSocket client for real-time cryptocurrency data feeds.
实时加密货币数据流WebSocket客户端

这个文件负责：
1. 连接到加密货币交易所的WebSocket API
2. 订阅实时价格数据流
3. 接收、验证和清理原始数据
4. 通过回调函数将处理后的数据传递给下游组件
"""
import asyncio
import json
import logging
import websockets
from typing import Dict, List, Optional, Callable
from datetime import datetime
from websockets.exceptions import ConnectionClosed, WebSocketException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CryptoFeedClient:
    """
    加密货币数据流客户端
    
    负责从Binance等交易所获取实时加密货币价格数据，
    通过WebSocket连接实现低延迟的数据传输。
    """
    
    def __init__(self, symbols: List[str], on_message_callback: Optional[Callable] = None):
        """
        Initialize the crypto feed client.
        初始化加密货币数据流客户端
        
        Args:
            symbols: List of cryptocurrency symbols to monitor (e.g., ["BTCUSDT", "ETHUSDT"])
                    要监控的加密货币符号列表
            on_message_callback: Optional callback function to handle received messages
                                处理接收消息的可选回调函数
        """
        # Convert symbols to Binance format (e.g., BTC-USD -> BTCUSDT)
        # 将符号转换为Binance格式（例如：BTC-USD -> BTCUSDT）
        self.symbols = [s.replace("-", "").replace("USD", "USDT").lower() for s in symbols]
        self.on_message_callback = on_message_callback  # 数据回调函数，用于传递给下游
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.reconnect_delay = 1  # Initial reconnect delay in seconds - 初始重连延迟（秒）
        self.max_reconnect_delay = 60  # Maximum reconnect delay in seconds - 最大重连延迟（秒）
        self._stop = False  # 停止标志
        self._connection_task = None  # 连接任务

    async def connect(self, uri: str = "wss://stream.binance.us:9443/ws"):
        """
        Establish WebSocket connection with retry mechanism.
        建立WebSocket连接，带重试机制
        
        Args:
            uri: WebSocket endpoint URI - WebSocket端点URI
        """
        self._stop = False
        self._connection_task = asyncio.create_task(self._connection_loop(uri))
        await self._connection_task

    async def _connection_loop(self, uri: str):
        """
        Internal connection loop with retry mechanism.
        内部连接循环，带重试机制
        
        实现自动重连和错误恢复，确保数据流的连续性
        """
        while not self._stop:
            try:
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    logger.info("Connected to WebSocket feed")
                    
                    # Subscribe to specified symbols
                    # 订阅指定的符号
                    await self._subscribe()
                    
                    # Reset reconnect delay on successful connection
                    # 成功连接后重置重连延迟
                    self.reconnect_delay = 1
                    
                    # Start message handling
                    # 开始消息处理
                    await self._handle_messages()
                    
            except (ConnectionClosed, WebSocketException) as e:
                if self._stop:
                    break
                logger.error(f"WebSocket connection error: {e}")
                await self._handle_reconnection()
                
            except Exception as e:
                if self._stop:
                    break
                logger.error(f"Unexpected error: {e}")
                await self._handle_reconnection()
            
            finally:
                self.is_connected = False
                self.websocket = None

    async def _subscribe(self):
        """
        Send subscription message for specified symbols.
        发送指定符号的订阅消息
        
        向交易所发送订阅请求，开始接收实时数据流
        """
        if not self.websocket or not self.is_connected:
            return
            
        # Create subscription message for each symbol
        # 为每个符号创建订阅消息
        streams = [f"{symbol}@ticker" for symbol in self.symbols]
        subscription_message = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }
        
        await self.websocket.send(json.dumps(subscription_message))
        logger.info(f"Subscribed to symbols: {self.symbols}")

    async def _handle_messages(self):
        """
        Handle incoming WebSocket messages.
        处理传入的WebSocket消息
        
        这是数据接收的核心循环，负责：
        1. 接收原始WebSocket消息
        2. 解析JSON数据
        3. 验证和清理数据
        4. 通过回调函数传递给下游
        """
        if not self.websocket or not self.is_connected:
            return
            
        try:
            async for message in self.websocket:
                if self._stop:
                    break
                    
                try:
                    data = json.loads(message)
                    
                    # Skip subscription responses
                    # 跳过订阅响应
                    if "result" in data:
                        continue
                    
                    # Validate and clean the data
                    # 验证和清理数据
                    cleaned_data = self._validate_and_clean_data(data)
                    
                    if cleaned_data and self.on_message_callback:
                        # 通过回调函数将清理后的数据传递给下游
                        await self.on_message_callback(cleaned_data)
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                
        except Exception as e:
            if not self._stop:
                logger.error(f"Error in message handling loop: {e}")
                raise

    def _validate_and_clean_data(self, data: Dict) -> Optional[Dict]:
        """
        Validate and clean received data.
        验证和清理接收到的数据
        
        将交易所的原始数据格式转换为标准化的内部格式，
        确保数据质量和一致性。
        
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
            if not all(field in data for field in required_fields):
                return None

            # Clean and format the data
            # 清理和格式化数据
            cleaned_data = {
                "symbol": data["s"],  # 符号
                "price": float(data["c"]),  # Using 'c' (current price) instead of 'p' (price change) - 使用'c'（当前价格）而不是'p'（价格变化）
                "timestamp": datetime.fromtimestamp(data["E"] / 1000),  # Convert from milliseconds - 从毫秒转换
                "volume_24h": float(data.get("v", 0)),  # 24小时交易量
                "sequence": int(data.get("E", 0))  # 序列号
            }

            return cleaned_data

        except (ValueError, KeyError) as e:
            logger.error(f"Error validating data: {e}")
            return None

    async def _handle_reconnection(self):
        """
        Handle reconnection with exponential backoff.
        处理重连，使用指数退避策略
        
        实现智能重连机制，避免频繁重连对服务器造成压力
        """
        if self._stop:
            return
            
        self.is_connected = False
        logger.info(f"Attempting to reconnect in {self.reconnect_delay} seconds...")
        await asyncio.sleep(self.reconnect_delay)
        
        # Implement exponential backoff
        # 实现指数退避
        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def close(self):
        """
        Close the WebSocket connection.
        关闭WebSocket连接
        
        优雅地关闭连接，清理资源，确保没有数据丢失
        """
        self._stop = True
        
        if self.websocket and self.is_connected:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket connection: {e}")
            
        if self._connection_task:
            try:
                self._connection_task.cancel()
                await asyncio.gather(self._connection_task, return_exceptions=True)
            except Exception as e:
                logger.error(f"Error cancelling connection task: {e}")
            
        self.websocket = None
        self.is_connected = False
        logger.info("WebSocket connection closed") 
"""
Example usage of the CryptoFeedClient with Kafka integration.
加密货币数据流集成示例 - 展示WebSocket客户端与Kafka生产者的协作

这个文件是整个数据摄入流程的协调器，负责：
1. 启动WebSocket客户端连接加密货币交易所
2. 初始化Kafka生产者连接消息队列
3. 建立数据流转管道：WebSocket → 回调函数 → Kafka
4. 处理优雅关闭和资源清理
"""
# 从 CryptoFeedClient（WebSocket）持续接收加密货币实时数据；
# 调用 CryptoKafkaProducer.send() 把数据发送到 Kafka；
# 你之前所有的 price_processor.py 和 price_anomaly_detector.py 正是依赖这些 Kafka 数据的；
# 自动处理优雅退出（Ctrl+C 结束也能清理资源）；

import asyncio
import logging
import signal
#引入平台判断和线程监听
import platform
import threading

# from .feed_client import CryptoFeedClient
from src.data_ingestion.crypto_feeds.feed_client import CryptoFeedClient
# 临时注释掉相对导入，避免ImportError
# from ..kafka_producer.crypto_producer import CryptoKafkaProducer
from src.data_ingestion.kafka_producer.crypto_producer import CryptoKafkaProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for cleanup
# 全局变量用于资源清理
client = None  # WebSocket客户端实例
kafka_producer = None  # Kafka生产者实例
shutdown_event = asyncio.Event()  # 关闭事件标志

async def handle_crypto_data(data):
    """
    Example callback function to handle received crypto data.
    处理接收到的加密货币数据的回调函数
    
    这是数据流转的关键节点：
    WebSocket接收数据 → 此函数处理 → 发送到Kafka
    
    Args:
        data: Cleaned cryptocurrency data dictionary
        data: 经过清理的加密货币数据字典
    """
    global kafka_producer
    
    # Log the received data
    # 记录接收到的数据
    logger.info(f"Received {data['symbol']} price: ${data['price']:.2f} at {data['timestamp']}")
    
    # Send data to Kafka if producer is available
    # 如果Kafka生产者可用，则发送数据到Kafka
    if kafka_producer:
        success = kafka_producer.send(data)  # 调用crypto_producer.py的send方法
        if not success:
            logger.error(f"Failed to send data to Kafka for {data['symbol']}")

async def shutdown(sig, loop):
    """
    Cleanup tasks tied to the service's shutdown.
    服务关闭时的清理任务
    
    确保所有资源都被正确释放：
    1. 关闭WebSocket连接
    2. 关闭Kafka生产者连接
    3. 取消所有异步任务
    """
    logger.info(f"Received exit signal {sig.name}...")
    shutdown_event.set()
    
    # Close WebSocket client
    # 关闭WebSocket客户端连接
    if client:
        logger.info("Closing WebSocket connection...")
        await client.close()  # 调用feed_client.py的close方法
    
    # Close Kafka producer
    # 关闭Kafka生产者连接
    if kafka_producer:
        logger.info("Closing Kafka producer...")
        kafka_producer.close()  # 调用crypto_producer.py的close方法
        
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        logger.info(f"Cancelling {len(tasks)} outstanding tasks")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

def handle_exception(loop, context):
    """
    Handle exceptions that escape the async tasks.
    处理异步任务中逃逸的异常
    
    提供全局异常处理，确保程序稳定运行
    """
    # Don't log cancelled errors during shutdown
    # 在关闭过程中不记录取消错误
    if "exception" in context and isinstance(context["exception"], asyncio.CancelledError):
        if not shutdown_event.is_set():
            logger.error("Task cancelled unexpectedly")
        return
        
    msg = context.get("exception", context["message"])
    logger.error(f"Caught exception: {msg}")

async def run_client():
    """
    Run the crypto feed client.
    运行加密货币数据流客户端
    
    这是主要的业务逻辑函数，负责：
    1. 初始化Kafka生产者
    2. 创建WebSocket客户端
    3. 建立数据流连接
    4. 处理连接生命周期
    """
    global client, kafka_producer
    
    try:
        # Initialize Kafka producer
        # 初始化Kafka生产者
        kafka_producer = CryptoKafkaProducer()  # 创建crypto_producer.py实例
        if not kafka_producer.connect():  # 连接到Kafka
            logger.error("Failed to connect to Kafka. Continuing without Kafka integration.")
            kafka_producer = None
        
        # Initialize the client with some popular cryptocurrency pairs
        # 使用流行的加密货币对初始化客户端
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD"]
        # 创建feed_client.py实例，传入回调函数
        client = CryptoFeedClient(symbols=symbols, on_message_callback=handle_crypto_data)
        
        # Connect to the WebSocket feed
        # 连接到WebSocket数据流
        await client.connect()  # 调用feed_client.py的connect方法
    except asyncio.CancelledError:
        logger.info("Client task cancelled")
    except Exception as e:
        logger.error(f"Error in client: {e}")
    finally:
        # 确保资源被清理
        if client:
            await client.close()
        if kafka_producer:
            kafka_producer.close()
    return True

async def main_async():
    """
    Async main function.
    异步主函数
    
    管理客户端任务的生命周期，处理任务取消和异常
    """
    # Create and run the client task
    # 创建并运行客户端任务
    client_task = asyncio.create_task(run_client())
    
    try:
        # Wait for the client task to complete or be cancelled
        # 等待客户端任务完成或被取消
        await client_task
    except asyncio.CancelledError:
        # Handle graceful shutdown
        # 处理优雅关闭
        if not client_task.done():
            client_task.cancel()
            await asyncio.wait([client_task])

def main():
    """
    Main entry point.
    主入口点
    
    设置事件循环、信号处理和异常处理，启动整个数据流服务
    """
    # Create and configure event loop
    # 创建并配置事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Handle exceptions
    # 处理异常
    loop.set_exception_handler(handle_exception)
    
    # # Register signal handlers
    # # 注册信号处理器
    # for sig in (signal.SIGTERM, signal.SIGINT):
    #     loop.add_signal_handler(
    #         sig,
    #         lambda s=sig: asyncio.create_task(shutdown(s, loop))
    #     )

# 在 Windows 系统中运行了 asyncio 的 loop.add_signal_handler()，但该方法在 Windows（尤其是非 WSL）下并不支持
    if platform.system() != 'Windows':
        # 非Windows系统：使用标准信号处理
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
    else:
        # Windows workaround: listen for KeyboardInterrupt in thread
        # Windows解决方案：在线程中监听键盘中断
        def windows_shutdown_listener():
            try:
                while not shutdown_event.is_set():
                    pass
            except KeyboardInterrupt:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(shutdown("SIGINT", loop)))

        threading.Thread(target=windows_shutdown_listener, daemon=True).start()
# ）————
    try:
        # 运行主异步函数
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Clean up
        # 清理资源
        try:
            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            logger.info("Successfully shutdown the crypto feed service.")

if __name__ == "__main__":
    main() 
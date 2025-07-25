"""
Example usage of the CryptoFeedClient with Kafka integration.
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

from .feed_client import CryptoFeedClient
from ..kafka_producer.crypto_producer import CryptoKafkaProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for cleanup
client = None
kafka_producer = None
shutdown_event = asyncio.Event()

async def handle_crypto_data(data):
    """
    Example callback function to handle received crypto data.
    
    Args:
        data: Cleaned cryptocurrency data dictionary
    """
    global kafka_producer
    
    # Log the received data
    logger.info(f"Received {data['symbol']} price: ${data['price']:.2f} at {data['timestamp']}")
    
    # Send data to Kafka if producer is available
    if kafka_producer:
        success = kafka_producer.send(data)
        if not success:
            logger.error(f"Failed to send data to Kafka for {data['symbol']}")

async def shutdown(sig, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {sig.name}...")
    shutdown_event.set()
    
    # Close WebSocket client
    if client:
        logger.info("Closing WebSocket connection...")
        await client.close()
    
    # Close Kafka producer
    if kafka_producer:
        logger.info("Closing Kafka producer...")
        kafka_producer.close()
        
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        logger.info(f"Cancelling {len(tasks)} outstanding tasks")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

def handle_exception(loop, context):
    """Handle exceptions that escape the async tasks."""
    # Don't log cancelled errors during shutdown
    if "exception" in context and isinstance(context["exception"], asyncio.CancelledError):
        if not shutdown_event.is_set():
            logger.error("Task cancelled unexpectedly")
        return
        
    msg = context.get("exception", context["message"])
    logger.error(f"Caught exception: {msg}")

async def run_client():
    """Run the crypto feed client."""
    global client, kafka_producer
    
    try:
        # Initialize Kafka producer
        kafka_producer = CryptoKafkaProducer()
        if not kafka_producer.connect():
            logger.error("Failed to connect to Kafka. Continuing without Kafka integration.")
            kafka_producer = None
        
        # Initialize the client with some popular cryptocurrency pairs
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD"]
        client = CryptoFeedClient(symbols=symbols, on_message_callback=handle_crypto_data)
        
        # Connect to the WebSocket feed
        await client.connect()
    except asyncio.CancelledError:
        logger.info("Client task cancelled")
    except Exception as e:
        logger.error(f"Error in client: {e}")
    finally:
        if client:
            await client.close()
        if kafka_producer:
            kafka_producer.close()
    return True

async def main_async():
    """Async main function."""
    # Create and run the client task
    client_task = asyncio.create_task(run_client())
    
    try:
        # Wait for the client task to complete or be cancelled
        await client_task
    except asyncio.CancelledError:
        # Handle graceful shutdown
        if not client_task.done():
            client_task.cancel()
            await asyncio.wait([client_task])

def main():
    """Main entry point."""
    # Create and configure event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Handle exceptions
    loop.set_exception_handler(handle_exception)
    
    # # Register signal handlers
    # for sig in (signal.SIGTERM, signal.SIGINT):
    #     loop.add_signal_handler(
    #         sig,
    #         lambda s=sig: asyncio.create_task(shutdown(s, loop))
    #     )

# 在 Windows 系统中运行了 asyncio 的 loop.add_signal_handler()，但该方法在 Windows（尤其是非 WSL）下并不支持
    if platform.system() != 'Windows':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
    else:
        # Windows workaround: listen for KeyboardInterrupt in thread
        def windows_shutdown_listener():
            try:
                while not shutdown_event.is_set():
                    pass
            except KeyboardInterrupt:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(shutdown("SIGINT", loop)))

        threading.Thread(target=windows_shutdown_listener, daemon=True).start()
# ）————
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Clean up
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
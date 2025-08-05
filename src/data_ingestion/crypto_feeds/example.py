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

# 环境感知的导入系统
import os
import sys
from pathlib import Path

# 检测运行环境
def detect_environment():
    """检测当前运行环境并设置正确的导入路径"""
    # 检查是否在 Airflow 容器中运行
    if os.path.exists('/opt/airflow'):
        # Airflow 环境
        project_root = '/opt/airflow/project-root'
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        return 'airflow'
        # 设置模块搜索路径 sys.path，加入 /opt/airflow/project-root
        # 这样 from src.XXX import YYY 才能正常导入
    else:
        # 本地开发环境
        # 获取当前文件的目录，向上找到项目根目录
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent # 定位 src/ 目录所在的路径
        if str(project_root) not in sys.path: #确保当前项目根目录（含有 src/ 的目录）被加入搜索路径中，避免导入失败
            sys.path.insert(0, str(project_root))
        return 'local'
# project_root	一个 Path 对象，指向项目根目录，比如 /Users/xiaoxi/my_project
# str(project_root)	将 Path 转为字符串路径
# sys.path	Python 用来搜索模块的目录列表，比如 import xxx 时会查这里

# 设置环境
ENVIRONMENT = detect_environment()

# 导入依赖
# 解释器会依次在 sys.path 里的路径中查找 src/ 目录。如果找不到就会报错
from src.data_ingestion.crypto_feeds.feed_client import CryptoFeedClient  #---> client
from src.data_ingestion.kafka_producer.crypto_producer import CryptoKafkaProducer  #---> kafka_producer

# 根据环境配置日志
if ENVIRONMENT == 'airflow':
    # Airflow 环境使用 Airflow 的日志系统
    from airflow.utils.log.logging_mixin import LoggingMixin
    logger = LoggingMixin().log
    # LoggingMixin 是 Airflow 提供的一个类，可以接入其日志框架（写入 Web UI、Log Server）
# LoggingMixin().log 会返回一个标准 logger 对象（和 logging.getLogger() 类似）

else:
    # 本地环境使用标准日志
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

logger.info(f"Running in {ENVIRONMENT} environment")

# Global variables for cleanup
# 全局变量用于资源清理
client = None  # WebSocket客户端实例
kafka_producer = None  # kafka_producer 是一个 Kafka 生产者实例，使用crypto_producer.py 中封装好的 Kafka 生产者类，
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
    shutdown_event.set() # 在最开头定义了，是 asyncio 提供的类似“通知机制”的工具，适用于多个异步任务之间的协调
    # .set() 向监听这个事件的任务广播：“现在是 True 了，可以退出了！”

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
        
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] # 把当前事件循环中所有还在跑的 task都找出来（除了当前正在执行 shutdown() 的 task 本身）
    if tasks:
        logger.info(f"Cancelling {len(tasks)} outstanding tasks")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)# asyncio.gather 返回一个协程对象，表示“多个任务组合”
        # 用 *tasks 是将列表“打散”为多个参数传入 gather（和 f(*args) 类似）
        # return_exceptions=True 如果任务抛出异常，不会引发 await 处的异常，而是把每个异常作为 gather() 返回列表中的元素返回

def handle_exception(loop, context): # 参数由 asyncio 异步事件循环系统自动生成并传入的
    # loop: 当前事件循环（asyncio.get_event_loop()）;context: 异常上下文字典（包含异常对象、出错信息、任务等）
    """
    Handle exceptions that escape the async tasks.
    处理异步任务中逃逸的异常
    
    提供全局异常处理，确保程序稳定运行
    """
    # Don't log cancelled errors during shutdown
    # 在关闭过程中不记录取消错误
    if "exception" in context and isinstance(context["exception"], asyncio.CancelledError): # context["exception"] 是不是一个 asyncio.CancelledError 类型的异常
    # asyncio.CancelledError 是 Python 异步任务在被取消（如 task.cancel()）时，自动抛出的异常。
        # context["exception"] 拿到真正的 Exception 对象
        if not shutdown_event.is_set(): # 如果 shutdown_event 不是 True，说明不是正常关闭，而是被外部信号中断
            logger.error("Task cancelled unexpectedly")
        return
        
    msg = context.get("exception", context["message"]) # 从字典 context 中取出 "exception" 对应的值，如果没有，就返回 "message" 对应的值。
    logger.error(f"Caught exception: {msg}")

# 主函数

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
        # Initialize Kafka producer with environment-aware configuration
        # 根据环境初始化Kafka生产者
        if ENVIRONMENT == 'airflow':
            # Airflow 容器环境使用容器内地址
            kafka_config = {'bootstrap_servers': 'kafka:29092'} # 传给 CryptoKafkaProducer(...) 构造函数，用来告诉它要连接哪个 Kafka 服务
        else:
            # 本地环境使用宿主机地址
            kafka_config = {'bootstrap_servers': 'localhost:9092'}

        #================调用CryptoKafkaProducer
        kafka_producer = CryptoKafkaProducer(**kafka_config)  # 创建crypto_producer.py实例,**kafka_config 会传入构造函数 __init__，告诉它连接哪个 Kafka 集群

        if not kafka_producer.connect():  # 连接到Kafka
            logger.error(f"Failed to connect to Kafka at {kafka_config['bootstrap_servers']}. Continuing without Kafka integration.")
            kafka_producer = None # 后续的代码会检查 if kafka_producer:，如果为 None，就不会尝试发送数据。
        else:
            logger.info(f"Successfully connected to Kafka at {kafka_config['bootstrap_servers']}") # 是一个配置参数，它指定了 Kafka 集群的地址（host:port），客户端用它来连接 Kafka 服务
        
        # Initialize the client with some popular cryptocurrency pairs
        # 使用流行的加密货币对初始化客户端
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD"] # 币种会传给 WebSocket 客户端，作为订阅的 ticker 列表
        # client 是一个 CryptoFeedClient 类的实例，它代表你的 WebSocket 客户端。会在 await client.connect() 后保持连接状态，启动数据流接收
        client = CryptoFeedClient(symbols=symbols, on_message_callback=handle_crypto_data)
        #================调用CryptoFeedClient
        # 传了一个函数参数 handle_crypto_data 给 
        #“每次有快递（数据）到，就打我电话（调用 handle_crypto_data，他的功能是把数据发送到 Kafka）。”
        # 把函数 handle_crypto_data() 当参数传进去了，给了 CryptoFeedClient。
        # 在 CryptoFeedClient 的代码里有：self.on_message_callback = on_message_callback
        # 它接住你传的那个函数，保存在 self.on_message_callback 中。




        # Connect to the WebSocket feed
        # 连接到WebSocket数据流
        await client.connect()  # 调用feed_client.py的connect方法
        # 真正开始连接 Binance WebSocket 数据源
        # 会启动 _connection_loop() → _handle_messages()，不断接收新数据并触发回调
        # 这是一个挂起点（async），会一直运行直到出错或关闭

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
    # 创建一个异步任务，并立即执行 run_client() 函数
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
    # Python 的 asyncio 是通过「事件循环（event loop）」来管理异步任务的。
    loop = asyncio.new_event_loop() # 创建一个新的事件循环对象
    asyncio.set_event_loop(loop) # 把这个新建的事件循环设置为当前线程的默认事件循环
    
    # Handle exceptions----
    # 处理异常
    loop.set_exception_handler(handle_exception) # 告诉 asyncio：“以后只要协程出现未捕获异常，就交给我 handle_exception() 来处理”。
    
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
# SIGINT	中断信号（Interrupt）	手动按 Ctrl+C
# SIGTERM	终止信号（Terminate）	操作系统或 Docker 停止进程
            # loop 是你在上面创建的 asyncio 事件循环对象： loop = asyncio.new_event_loop()
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
            # 如果程序收到一个操作系统信号（比如你按下 Ctrl+C，也就是 SIGINT），就运行 shutdown(s, loop) 这个协程
    else:
        # Windows workaround: listen for KeyboardInterrupt in thread
        # Windows解决方案：在线程中监听键盘中断
        def windows_shutdown_listener():
            try: # 死循环监控，有点像“后台看门人”
                while not shutdown_event.is_set():
                    pass
            except KeyboardInterrupt: #  Ctrl+C，会触发 Python 的 KeyboardInterrupt 异常。
                loop.call_soon_threadsafe(lambda: asyncio.create_task(shutdown("SIGINT", loop))) #有两个“人”：一个是后台线程（windows_shutdown_listener），一个是主线程（asyncio 在运行）。用 loop.call_soon_threadsafe(...)：偷偷往主线程“任务队列”塞一个任务

        threading.Thread(target=windows_shutdown_listener, daemon=True).start() # threading.Thread(...).start()这就是开启一个后台线程。这个线程运行的是 windows_shutdown_listener()。
    try:
        # 运行主异步函数
        loop.run_until_complete(main_async())# loop 是一个 事件循环对象，是 asyncio 程序的大脑。
        #loop 就像是电影院的“排片系统”
        # main_async() 是一部电影（比如《币价大冒险》）
        # loop.run_until_complete(main_async()) 就是说：
        # “现在放这部电影，一直放，直到它演完为止”
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Clean up
        # 清理资源
        try:
            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            # 我把上面那些没完成的任务 pending 打包一起 await 一下（用 asyncio.gather(...)）
            # return_exceptions=True 的作用是：即使某些任务报错了，也不要中断其它的，全部执行完我再处理
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens()) # loop.shutdown_asyncgens()	关闭所有未完成的 async generator
            loop.close()
            logger.info("Successfully shutdown the crypto feed service.")

if __name__ == "__main__":
    main() 
# 1自己运行这个文件：__name__ == "__main__" 就是 True，于是就会调用：main() 
# 2如果被别人 import那么 __name__ 会变成模块名，比如 "my_project.crypto_pipeline"，就 不会自动执行 main()，只会加载函数和类，供调用。
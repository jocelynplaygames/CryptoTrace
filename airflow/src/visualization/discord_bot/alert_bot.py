# ✅ 从 .env 加载 Discord token 和 Kafka 地址；
# ✅ 自动监听 Kafka crypto_price_anomalies 主题；
# ✅ 把异常消息格式化后发送到 Discord 指定频道；
# ✅ 提供 !status 和 !help 命令。
import discord
from discord.ext import commands, tasks
from kafka import KafkaConsumer
import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#继承自 commands.Bot，是整个机器人的核心类
class CryptoAlertBot(commands.Bot):
    def __init__(
        self,
        command_prefix: str,
        alert_channel_id: int,
        bootstrap_servers: list,
        topic: str
    ):
        """
        Initialize the Crypto Alert Bot.
        
        Args:
            command_prefix: Command prefix for bot commands
            alert_channel_id: Discord channel ID for sending alerts
            bootstrap_servers: List of Kafka broker addresses
            topic: Kafka topic to consume anomaly alerts from
        """
        intents = discord.Intents.default()
        intents.message_content = True
        # super().__init__(command_prefix=command_prefix, intents=intents)
        #禁用commands.Bot默认的 help 命令
        super().__init__(command_prefix=command_prefix, intents=intents, help_command=None)
        
        self.alert_channel_id = alert_channel_id
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            group_id='discord_alert_bot'
        )
        
        

    #注册 bot 的命令，如 !status 和 !help。
    async def setup_hook(self):
        """Set up the bot with initial commands."""
        @self.command(name='status')
        async def status(ctx):
            """Check if the bot is running and monitoring alerts."""
            await ctx.send("🟢 Bot is running and monitoring crypto price anomalies!")

        #但commands.Bot 是 Discord.py 提供的一个封装类，它默认带有一个 help 命令，所以当你又注册了一个叫 help 的命令，就导致命令名冲突（重复注册），抛出了 CommandRegistrationError
        @self.command(name='help')
        async def help_command(ctx):
            """Display help information."""
            help_text = """
            **Crypto Alert Bot Commands**
            `!status` - Check if the bot is running
            `!help` - Display this help message
            
            The bot automatically sends alerts when crypto price anomalies are detected.
            """
            await ctx.send(help_text)
        
        # Start the alert checking loop
        self.check_alerts.start() # .start() 启动loop异步任务

    def format_alert_message(self, alert_data: Dict) -> str:
        """Format the alert data into a Discord message."""
        severity_emoji = "🔴" if alert_data['severity'] == 'high' else "🟡"
        
        return f"""
{severity_emoji} **Crypto Price Anomaly Detected!**

**Symbol:** {alert_data['symbol']}
**Current Price:** ${alert_data['current_price']:.2f}
**Price Change:** {alert_data['price_change_pct']:.2f}%
**Z-Score:** {alert_data['z_score']:.2f}
**Severity:** {alert_data['severity'].upper()}
**Time:** {datetime.fromisoformat(alert_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S UTC')}

{'⚠️ **URGENT:** Extreme price movement detected!' if alert_data['severity'] == 'high' else ''}
"""

    #后台循环任务开始监听 Kafka（每秒执行一次）
    @tasks.loop(seconds=1) #定义了一个定时异步任务
    async def check_alerts(self):
        """Check for new alerts from Kafka and send them to Discord."""
        try:
            # Wait until the bot is ready
            await self.wait_until_ready()
            
            # Get the alert channel
            channel = self.get_channel(self.alert_channel_id)
            if not channel:
                logger.error(f"Could not find channel with ID {self.alert_channel_id}")
                return
            
            # # Check for new messages
            # for message in self.consumer: #是阻塞式的无限迭代器
            #     alert_data = message.value
            #     alert_message = self.format_alert_message(alert_data)

            # 用 poll() 替换 for message in self.consumer:
            
            records = self.consumer.poll(timeout_ms = 100) # 非阻塞拉取消息
            #Kafka 会在 100 毫秒内尝试获取消息，如果没有消息会立刻返回，不阻塞主线程。
            for tp, messages in records.items():
                for message in messages:
                    alert_data = message.value
                    alert_message = self.format_alert_message(alert_data)
                
                
                try:
                    await channel.send(alert_message)
                    logger.info(f"Sent alert for {alert_data['symbol']}")
                except Exception as e:
                    logger.error(f"Error sending Discord message: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error in check_alerts: {str(e)}")

    #在 Bot 登录成功时触发一次（打印一些启动日志）
    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Logged in as {self.user.name}")
        logger.info("Bot is ready to send alerts!")

        # 测试能否发送消息
        channel = self.get_channel(self.alert_channel_id)
        if channel:
            await channel.send("✅ Bot 已上线，可发送消息！")
        else:
            logger.error("❌ 找不到指定频道 ID")

# 加载配置，为 bot 启动做好准备。
def run_bot():
    """Run the Discord bot."""
    # Get configuration from environment variables
    #通过 os.getenv() 从 .env 中加载 Kafka 和 Discord 的配置项
    #os.getenv() 只会从 系统的环境变量 中读取值。它并不会自动从 .env 文件中加载内容
    #我增加使用 python-dotenv 来自动加载 .env 文件
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
    # KAFKA_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092').split(',')
    KAFKA_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'host.docker.internal:9092').split(',')

    
    if not TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN environment variable is not set")
    
    if not CHANNEL_ID:
        raise ValueError("DISCORD_CHANNEL_ID environment variable is not set")
    
    # Create and run the bot
    bot = CryptoAlertBot(
        command_prefix="!",
        alert_channel_id=CHANNEL_ID,
        bootstrap_servers=KAFKA_SERVERS,
        topic='crypto_price_anomalies'
    )
    
    bot.run(TOKEN) #启动 Discord Bot（事件循环正式开始）

if __name__ == "__main__":
    run_bot() 
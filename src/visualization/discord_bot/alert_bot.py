# ✅ 从 .env 加载 Discord token 和 Kafka 地址；
# ✅ 自动监听 Kafka crypto_price_anomalies 主题；
# ✅ 把异常消息格式化后发送到 Discord 指定频道；
# ✅ 提供 !status 和 !help 命令。
import discord
from discord.ext import commands, tasks
from confluent_kafka import Consumer
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
        bootstrap_servers: str,
        anomaly_topic: str,
        analytics_topic: str = "crypto_analytics"
    ):
        """
        Initialize the Crypto Alert Bot.
        
        Args:
            command_prefix: Command prefix for bot commands
            alert_channel_id: Discord channel ID for sending alerts
            bootstrap_servers: String of Kafka broker addresses (comma-separated)
            topic: Kafka topic to consume anomaly alerts from
        """
        intents = discord.Intents.default()
        intents.message_content = True
        # super().__init__(command_prefix=command_prefix, intents=intents)
        #禁用commands.Bot默认的 help 命令
        super().__init__(command_prefix=command_prefix, intents=intents, help_command=None)
        
        self.alert_channel_id = alert_channel_id
        self.analytics_topic = analytics_topic
        
        # 异常警报消费者
        anomaly_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': 'discord_anomaly_bot',
            'auto.offset.reset': 'latest'
        }
        self.anomaly_consumer = Consumer(anomaly_config)
        self.anomaly_consumer.subscribe([anomaly_topic])
        
        # 分析数据消费者
        analytics_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': 'discord_analytics_bot',
            'auto.offset.reset': 'latest'
        }
        self.analytics_consumer = Consumer(analytics_config)
        self.analytics_consumer.subscribe([analytics_topic])
        
        # 24小时价格变化阈值
        self.price_change_threshold = 5.0  # 5%变化阈值
        self.last_24h_notification = {}  # 记录每个币种的最后通知时间
        
        

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

    def format_24h_change_message(self, analytics_data: Dict) -> str:
        """Format the 24h price change data into a Discord message."""
        symbol = analytics_data['symbol']
        price_change_24h = analytics_data.get('price_change_24h', 0.0)
        
        # 根据变化幅度选择emoji
        if abs(price_change_24h) >= 10:
            emoji = "🚨"  # 大幅变化
        elif abs(price_change_24h) >= 5:
            emoji = "⚠️"  # 中等变化
        elif price_change_24h > 0:
            emoji = "📈"  # 小幅上涨
        elif price_change_24h < 0:
            emoji = "📉"  # 小幅下跌
        else:
            emoji = "➡️"  # 无变化
        
        current_price = analytics_data.get('average_price', 0.0)
        
        return f"""
{emoji} **24-Hour Price Change Alert**

**Symbol:** {symbol.upper()}
**Current Price:** ${current_price:.2f}
**24h Change:** {price_change_24h:+.2f}%
**Time:** {datetime.fromisoformat(analytics_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S UTC')}

{'🔥 **Significant movement detected!**' if abs(price_change_24h) >= self.price_change_threshold else '📊 Regular market update'}
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
            
            # 检查异常警报
            anomaly_records = self.anomaly_consumer.poll(timeout=0.1)
            if anomaly_records:
                for tp, messages in anomaly_records.items():
                    for message in messages:
                        alert_data = json.loads(message.value().decode('utf-8'))
                        alert_message = self.format_alert_message(alert_data)
                        
                        try:
                            await channel.send(alert_message)
                            logger.info(f"Sent anomaly alert for {alert_data['symbol']}")
                        except Exception as e:
                            logger.error(f"Error sending Discord message: {str(e)}")
            
            # 检查24小时价格变化
            analytics_records = self.analytics_consumer.poll(timeout=0.1)
            if analytics_records:
                for tp, messages in analytics_records.items():
                    for message in messages:
                        analytics_data = json.loads(message.value().decode('utf-8'))
                        symbol = analytics_data.get('symbol', '')
                        price_change_24h = analytics_data.get('price_change_24h', 0.0)
                        
                        # 检查是否需要发送24小时变化通知
                        current_time = datetime.now()
                        last_notification = self.last_24h_notification.get(symbol)
                        
                        # 如果变化超过阈值且距离上次通知超过1小时，则发送通知
                        if (abs(price_change_24h) >= self.price_change_threshold and 
                            (last_notification is None or 
                             (current_time - last_notification).total_seconds() > 3600)):
                            
                            change_message = self.format_24h_change_message(analytics_data)
                            
                            try:
                                await channel.send(change_message)
                                self.last_24h_notification[symbol] = current_time
                                logger.info(f"Sent 24h change alert for {symbol}: {price_change_24h:.2f}%")
                            except Exception as e:
                                logger.error(f"Error sending 24h change Discord message: {str(e)}")
                
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
def main():
    """Run the Discord bot."""
    # Get configuration from environment variables
    #通过 os.getenv() 从 .env 中加载 Kafka 和 Discord 的配置项
    #os.getenv() 只会从 系统的环境变量 中读取值。它并不会自动从 .env 文件中加载内容
    #我增加使用 python-dotenv 来自动加载 .env 文件
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
    # KAFKA_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'host.docker.internal:9092')

    
    if not TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN environment variable is not set")
    
    if not CHANNEL_ID:
        raise ValueError("DISCORD_CHANNEL_ID environment variable is not set")
    
    # Create and run the bot
    bot = CryptoAlertBot(
        command_prefix="!",
        alert_channel_id=CHANNEL_ID,
        bootstrap_servers=KAFKA_SERVERS,
        anomaly_topic='crypto_price_anomalies',
        analytics_topic='crypto_analytics'
    )
    
    bot.run(TOKEN) #启动 Discord Bot（事件循环正式开始）

if __name__ == "__main__":
    main() 
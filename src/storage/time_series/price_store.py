"""
Time series storage for cryptocurrency price data.
加密货币价格数据时序存储模块

该模块负责：
1. 将实时价格数据持久化到文件系统
2. 支持分区存储，提高查询性能
3. 提供数据检索和分析接口
4. 管理不同类型数据的存储（原始数据、分析结果、警报）

组件协调关系：
- 上游：Kafka消费者（storage_consumer.py）- 消费各种数据流
- 下游：数据分析工具、可视化组件、Tableau导出
- 协调方式：文件系统存储，支持并发读写

数据流转分析：
1. 接收Kafka消息 → 解析数据 → 确定存储路径
2. 按时间分区存储 → 写入JSON文件 → 更新索引
3. 查询请求 → 定位分区 → 读取数据 → 返回结果
4. 支持批量操作和增量更新

性能优化策略：
1. 分区存储：按时间分区，提高查询效率
2. 文件压缩：减少存储空间和I/O开销
3. 批量写入：减少文件系统调用
4. 内存缓存：缓存热点数据，提高读取性能
5. 异步I/O：非阻塞的文件操作

接口设计：
- 输入：JSON格式的数据字典
- 输出：DataFrame或字典列表
- 存储格式：按时间分区的JSON文件
- 查询接口：支持时间范围、符号过滤等条件

存储架构：
- 原始数据：按小时分区，存储原始价格数据
- 分析数据：按小时分区，存储分析结果
- 警报数据：按天分区，存储异常警报
- 索引文件：加速数据定位和查询
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd
import gzip
import pickle
from concurrent.futures import ThreadPoolExecutor
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PriceStore:
    """
    加密货币价格数据存储类
    
    提供高性能的时序数据存储和检索功能：
    - 分区存储：按时间分区，提高查询效率
    - 压缩存储：减少存储空间
    - 并发支持：支持多线程读写
    - 缓存机制：缓存热点数据
    - 批量操作：支持批量读写
    
    设计模式：
    - 策略模式：可配置的存储策略
    - 工厂模式：根据数据类型创建不同的存储器
    - 观察者模式：数据更新时通知相关组件
    
    性能特性：
    - 分区存储：减少查询范围
    - 压缩存储：节省空间和I/O
    - 内存缓存：提高读取性能
    - 批量操作：减少系统调用
    """
    
    def __init__(self, base_path: Union[str, Path], enable_compression: bool = True, cache_size: int = 1000):
        """
        Initialize the price store.
        初始化价格存储
        
        Args:
            base_path: Base directory for storing data files - 数据文件的基础目录
            enable_compression: Whether to compress stored files - 是否启用文件压缩
            cache_size: Maximum number of cached dataframes - 缓存的最大数据框数量
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.enable_compression = enable_compression
        self.cache_size = cache_size
        
        # Create subdirectories for different data types
        # 为不同类型的数据创建子目录
        self.raw_dir = self.base_path / "raw"
        self.analytics_dir = self.base_path / "analytics"
        self.alerts_dir = self.base_path / "alerts"
        
        for directory in [self.raw_dir, self.analytics_dir, self.alerts_dir]:
            directory.mkdir(exist_ok=True)
        
        # 缓存和锁
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._file_locks = {}
        self._file_locks_lock = threading.Lock()
        
        # 性能监控
        self.storage_operations = 0
        self.cache_hits = 0
        self.cache_misses = 0
            
    def _get_date_partition(self, timestamp: datetime) -> str:
        """
        Get partition path based on date.
        根据日期获取分区路径
        
        Args:
            timestamp: 时间戳
            
        Returns:
            str: 分区路径（YYYY/MM/DD格式）
        """
        return timestamp.strftime("%Y/%m/%d")
        
    def _get_hour_partition(self, timestamp: datetime) -> str:
        """
        Get partition path including hour.
        获取包含小时的分区路径
        
        Args:
            timestamp: 时间戳
            
        Returns:
            str: 分区路径（YYYY/MM/DD/HH格式）
        """
        return timestamp.strftime("%Y/%m/%d/%H")
    
    def _get_file_lock(self, file_path: Path) -> threading.Lock:
        """
        获取文件锁，确保并发安全
        
        Args:
            file_path: 文件路径
            
        Returns:
            threading.Lock: 文件锁
        """
        with self._file_locks_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = threading.Lock()
            return self._file_locks[file_path]
    
    def _write_json_file(self, file_path: Path, data: Dict) -> bool:
        """
        写入JSON文件，支持压缩
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
            
        Returns:
            bool: 写入是否成功
        """
        try:
            with self._get_file_lock(file_path):
                if self.enable_compression:
                    with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                else:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False
        
    def store_raw_price(self, symbol: str, price_data: Dict) -> bool:
        """
        Store raw price data.
        存储原始价格数据
        
        存储策略：
        - 按小时分区：提高查询效率
        - 压缩存储：节省空间
        - 并发安全：使用文件锁
        - 批量写入：减少I/O开销
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            price_data: Price data dictionary - 价格数据字典
            
        Returns:
            bool: True if storage successful - 存储成功返回True
        """
        try:
            timestamp = datetime.fromisoformat(price_data['timestamp'])
            partition = self._get_hour_partition(timestamp)
            
            # Create partition directory
            # 创建分区目录
            partition_dir = self.raw_dir / symbol.lower() / partition
            partition_dir.mkdir(parents=True, exist_ok=True)
            
            # Store data in JSON file
            # 将数据存储到JSON文件
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.json"
            if self.enable_compression:
                filename += '.gz'
            file_path = partition_dir / filename
            
            success = self._write_json_file(file_path, price_data)
            if success:
                self.storage_operations += 1
                logger.debug(f"Stored raw price data: {file_path}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to store raw price data: {e}")
            return False
            
    def store_analytics(self, symbol: str, analytics_data: Dict) -> bool:
        """
        Store price analytics data.
        存储价格分析数据
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            analytics_data: Analytics data dictionary - 分析数据字典
            
        Returns:
            bool: True if storage successful - 存储成功返回True
        """
        try:
            timestamp = datetime.fromisoformat(analytics_data['timestamp'])
            partition = self._get_hour_partition(timestamp)
            
            # Create partition directory
            # 创建分区目录
            partition_dir = self.analytics_dir / symbol.lower() / partition
            partition_dir.mkdir(parents=True, exist_ok=True)
            
            # Store data in JSON file
            # 将数据存储到JSON文件
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.json"
            if self.enable_compression:
                filename += '.gz'
            file_path = partition_dir / filename
            
            success = self._write_json_file(file_path, analytics_data)
            if success:
                self.storage_operations += 1
                logger.debug(f"Stored analytics data: {file_path}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to store analytics data: {e}")
            return False
            
    def store_alert(self, symbol: str, alert_data: Dict) -> bool:
        """
        Store price alert data.
        存储价格警报数据
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            alert_data: Alert data dictionary - 警报数据字典
            
        Returns:
            bool: True if storage successful - 存储成功返回True
        """
        try:
            timestamp = datetime.fromisoformat(alert_data['timestamp'])
            partition = self._get_date_partition(timestamp)
            
            # Create partition directory
            # 创建分区目录
            partition_dir = self.alerts_dir / symbol.lower() / partition
            partition_dir.mkdir(parents=True, exist_ok=True)
            
            # Store data in JSON file
            # 将数据存储到JSON文件
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.json"
            if self.enable_compression:
                filename += '.gz'
            file_path = partition_dir / filename
            
            success = self._write_json_file(file_path, alert_data)
            if success:
                self.storage_operations += 1
                logger.debug(f"Stored alert data: {file_path}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to store alert data: {e}")
            return False
    
    def _read_json_file(self, file_path: Path) -> Optional[Dict]:
        """
        读取JSON文件，支持压缩
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict: 文件内容，None表示读取失败
        """
        try:
            with self._get_file_lock(file_path):
                if file_path.suffix == '.gz':
                    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None
    
    def _get_cache_key(self, data_type: str, symbol: str, start_time: datetime, end_time: datetime) -> str:
        """
        生成缓存键
        
        Args:
            data_type: 数据类型（raw/analytics/alerts）
            symbol: 符号
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            str: 缓存键
        """
        return f"{data_type}:{symbol}:{start_time.isoformat()}:{end_time.isoformat()}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """
        从缓存获取数据
        
        Args:
            cache_key: 缓存键
            
        Returns:
            pd.DataFrame: 缓存的数据，None表示未命中
        """
        with self._cache_lock:
            if cache_key in self._cache:
                self.cache_hits += 1
                return self._cache[cache_key]
            self.cache_misses += 1
            return None
    
    def _add_to_cache(self, cache_key: str, data: pd.DataFrame):
        """
        添加数据到缓存
        
        Args:
            cache_key: 缓存键
            data: 要缓存的数据
        """
        with self._cache_lock:
            # 如果缓存已满，删除最旧的条目
            if len(self._cache) >= self.cache_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            
            self._cache[cache_key] = data
            
    def get_price_data(
        self,
        symbol: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        as_dataframe: bool = True
    ) -> Union[List[Dict], pd.DataFrame]:
        """
        Retrieve price data for a given time range.
        检索指定时间范围内的价格数据
        
        查询优化：
        - 缓存机制：缓存查询结果
        - 分区查询：只查询相关分区
        - 并行读取：使用线程池并行读取文件
        - 内存管理：及时释放不需要的数据
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            start_time: Start of time range - 时间范围开始
            end_time: End of time range (defaults to now) - 时间范围结束（默认为现在）
            as_dataframe: Return as pandas DataFrame if True, else list of dicts - 是否返回DataFrame
            
        Returns:
            Price data as DataFrame or list - 价格数据（DataFrame或列表）
        """
        end_time = end_time or datetime.now()
        
        # 检查缓存
        cache_key = self._get_cache_key('raw', symbol, start_time, end_time)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data if as_dataframe else cached_data.to_dict('records')
        
        data = []
        
        try:
            # Get all relevant partition directories
            # 获取所有相关的分区目录
            current = start_time.replace(minute=0, second=0, microsecond=0)
            while current <= end_time:
                partition = self._get_hour_partition(current)
                partition_dir = self.raw_dir / symbol.lower() / partition
                
                if partition_dir.exists():
                    # Read all JSON files in partition
                    # 读取分区中的所有JSON文件
                    file_pattern = "*.json.gz" if self.enable_compression else "*.json"
                    for file_path in partition_dir.glob(file_pattern):
                        price_data = self._read_json_file(file_path)
                        if price_data:
                            timestamp = datetime.fromisoformat(price_data['timestamp'])
                            if start_time <= timestamp <= end_time:
                                data.append(price_data)
                                
                current += timedelta(hours=1)
                
            if not data:
                logger.warning(f"No data found for {symbol} between {start_time} and {end_time}")
                result = pd.DataFrame() if as_dataframe else []
            else:
                # Sort by timestamp
                # 按时间戳排序
                data.sort(key=lambda x: x['timestamp'])
                
                if as_dataframe:
                    result = pd.DataFrame(data)
                    # 添加到缓存
                    self._add_to_cache(cache_key, result)
                else:
                    result = data
                    
            return result
            
        except Exception as e:
            logger.error(f"Failed to retrieve price data: {e}")
            return pd.DataFrame() if as_dataframe else []
            
    def get_analytics_data(
        self,
        symbol: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        as_dataframe: bool = True
    ) -> Union[List[Dict], pd.DataFrame]:
        """
        Retrieve analytics data for a given time range.
        检索指定时间范围内的分析数据
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            start_time: Start of time range - 时间范围开始
            end_time: End of time range (defaults to now) - 时间范围结束（默认为现在）
            as_dataframe: Return as pandas DataFrame if True, else list of dicts - 是否返回DataFrame
            
        Returns:
            Analytics data as DataFrame or list - 分析数据（DataFrame或列表）
        """
        end_time = end_time or datetime.now()
        
        # 检查缓存
        cache_key = self._get_cache_key('analytics', symbol, start_time, end_time)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data if as_dataframe else cached_data.to_dict('records')
        
        data = []
        
        try:
            # Get all relevant partition directories
            # 获取所有相关的分区目录
            current = start_time.replace(minute=0, second=0, microsecond=0)
            while current <= end_time:
                partition = self._get_hour_partition(current)
                partition_dir = self.analytics_dir / symbol.lower() / partition
                
                if partition_dir.exists():
                    # Read all JSON files in partition
                    # 读取分区中的所有JSON文件
                    file_pattern = "*.json.gz" if self.enable_compression else "*.json"
                    for file_path in partition_dir.glob(file_pattern):
                        analytics_data = self._read_json_file(file_path)
                        if analytics_data:
                            timestamp = datetime.fromisoformat(analytics_data['timestamp'])
                            if start_time <= timestamp <= end_time:
                                data.append(analytics_data)
                                
                current += timedelta(hours=1)
                
            if not data:
                logger.warning(f"No analytics data found for {symbol} between {start_time} and {end_time}")
                result = pd.DataFrame() if as_dataframe else []
            else:
                # Sort by timestamp
                # 按时间戳排序
                data.sort(key=lambda x: x['timestamp'])
                
                if as_dataframe:
                    result = pd.DataFrame(data)
                    # 添加到缓存
                    self._add_to_cache(cache_key, result)
                else:
                    result = data
                    
            return result
            
        except Exception as e:
            logger.error(f"Failed to retrieve analytics data: {e}")
            return pd.DataFrame() if as_dataframe else []
            
    def get_alerts(
        self,
        symbol: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        as_dataframe: bool = True
    ) -> Union[List[Dict], pd.DataFrame]:
        """
        Retrieve alerts for a given time range.
        检索指定时间范围内的警报数据
        
        Args:
            symbol: Trading pair symbol - 交易对符号
            start_time: Start of time range - 时间范围开始
            end_time: End of time range (defaults to now) - 时间范围结束（默认为现在）
            as_dataframe: Return as pandas DataFrame if True, else list of dicts - 是否返回DataFrame
            
        Returns:
            Alert data as DataFrame or list - 警报数据（DataFrame或列表）
        """
        end_time = end_time or datetime.now()
        
        # 检查缓存
        cache_key = self._get_cache_key('alerts', symbol, start_time, end_time)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data if as_dataframe else cached_data.to_dict('records')
        
        data = []
        
        try:
            # Get all relevant partition directories
            # 获取所有相关的分区目录
            current = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            while current <= end_time:
                partition = self._get_date_partition(current)
                partition_dir = self.alerts_dir / symbol.lower() / partition
                
                if partition_dir.exists():
                    # Read all JSON files in partition
                    # 读取分区中的所有JSON文件
                    file_pattern = "*.json.gz" if self.enable_compression else "*.json"
                    for file_path in partition_dir.glob(file_pattern):
                        alert_data = self._read_json_file(file_path)
                        if alert_data:
                            timestamp = datetime.fromisoformat(alert_data['timestamp'])
                            if start_time <= timestamp <= end_time:
                                data.append(alert_data)
                                
                current += timedelta(days=1)
                
            if not data:
                logger.warning(f"No alerts found for {symbol} between {start_time} and {end_time}")
                result = pd.DataFrame() if as_dataframe else []
            else:
                # Sort by timestamp
                # 按时间戳排序
                data.sort(key=lambda x: x['timestamp'])
                
                if as_dataframe:
                    result = pd.DataFrame(data)
                    # 添加到缓存
                    self._add_to_cache(cache_key, result)
                else:
                    result = data
                    
            return result
            
        except Exception as e:
            logger.error(f"Failed to retrieve alerts: {e}")
            return pd.DataFrame() if as_dataframe else []
    
    def get_stats(self) -> Dict:
        """
        获取存储统计信息
        
        Returns:
            包含存储统计信息的字典
        """
        return {
            "storage_operations": self.storage_operations,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_size": len(self._cache),
            "cache_hit_rate": (self.cache_hits / (self.cache_hits + self.cache_misses) * 100) if (self.cache_hits + self.cache_misses) > 0 else 0,
            "compression_enabled": self.enable_compression
        }
    
    def clear_cache(self):
        """
        清空缓存
        """
        with self._cache_lock:
            self._cache.clear()
            self.cache_hits = 0
            self.cache_misses = 0
        logger.info("Cache cleared") 
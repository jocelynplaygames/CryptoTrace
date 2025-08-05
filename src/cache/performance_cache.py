"""
High Performance Caching System

This module is responsible for:
1. Multi-level caching strategy (Memory + Redis)
2. Intelligent cache invalidation and updates
3. Cache hit rate optimization
4. Distributed cache support

Performance improvement targets:
- Response speed improvement: 40-60%
- Cache hit rate: 85%+
- Database query reduction: 80%+
"""
import redis
import json
import pickle
import hashlib
import time
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
from functools import wraps
import threading
from collections import OrderedDict

logger = logging.getLogger(__name__)

class LRUCache:
    """LRU Cache Implementation"""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self.cache = OrderedDict()
        self.lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return self.cache[key]
            return None
    
    def set(self, key: str, value: Any):
        with self.lock:
            if key in self.cache:
                # Update existing value
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                # Add new value
                self.cache[key] = value
                # If exceeds max size, remove oldest
                if len(self.cache) > self.maxsize:
                    self.cache.popitem(last=False)
    
    def delete(self, key: str):
        with self.lock:
            self.cache.pop(key, None)
    
    def clear(self):
        with self.lock:
            self.cache.clear()
    
    def size(self) -> int:
        return len(self.cache)

class PerformanceCache:
    """
    High Performance Caching System
    
    Features:
    - Multi-level cache: Memory + Redis
    - Intelligent TTL management
    - Cache warm-up
    - Statistics monitoring
    """
    
    def __init__(self, 
                 redis_host: str = 'localhost',
                 redis_port: int = 6379,
                 redis_db: int = 0,
                 memory_cache_size: int = 10000,
                 default_ttl: int = 300):  # 5 minutes default TTL
        """
        Initialize caching system
        
        Args:
            redis_host: Redis server address
            redis_port: Redis port
            redis_db: Redis database number
            memory_cache_size: Memory cache size
            default_ttl: Default cache time (seconds)
        """
        self.default_ttl = default_ttl
        self.memory_cache = LRUCache(memory_cache_size)
        
        # Redis connection
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self.redis_available = False
            self.redis_client = None
        
        # Statistics
        self.stats = {
            'memory_hits': 0,
            'redis_hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }
        self.stats_lock = threading.Lock()
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key from prefix and arguments
        
        Args:
            prefix: Key prefix
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Generated cache key
        """
        key_parts = [prefix]
        
        # Add positional arguments
        for arg in args:
            key_parts.append(str(arg))
        
        # Add keyword arguments (sorted for consistency)
        for key, value in sorted(kwargs.items()):
            key_parts.append(f"{key}:{value}")
        
        # Create hash for long keys
        key_string = "_".join(key_parts)
        if len(key_string) > 100:
            return hashlib.md5(key_string.encode()).hexdigest()
        
        return key_string
    
    def get(self, key: str, use_memory: bool = True) -> Optional[Any]:
        """
        Get cached value
        
        Args:
            key: Cache key
            use_memory: Whether to use memory cache
            
        Returns:
            Cached value or None
        """
        # First check memory cache
        if use_memory:
            value = self.memory_cache.get(key)
            if value is not None:
                with self.stats_lock:
                    self.stats['memory_hits'] += 1
                return value
        
        # Check Redis cache
        if self.redis_available:
            try:
                value = self.redis_client.get(key)
                if value is not None:
                    deserialized = pickle.loads(value)
                    if use_memory:
                        self.memory_cache.set(key, deserialized)
                    with self.stats_lock:
                        self.stats['redis_hits'] += 1
                    return deserialized
                else:
                    with self.stats_lock:
                        self.stats['misses'] += 1
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")
                with self.stats_lock:
                    self.stats['misses'] += 1
        else:
            with self.stats_lock:
                self.stats['misses'] += 1
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None, use_memory: bool = True):
        """
        Set cache value
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live (seconds)
            use_memory: Whether to use memory cache
        """
        ttl = ttl or self.default_ttl
        
        # Set in memory cache
        if use_memory:
            self.memory_cache.set(key, value)
        
        # Set in Redis cache
        if self.redis_available:
            try:
                serialized = pickle.dumps(value)
                self.redis_client.setex(key, ttl, serialized)
                with self.stats_lock:
                    self.stats['sets'] += 1
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")
        else:
            with self.stats_lock:
                self.stats['sets'] += 1
    
    def delete(self, key: str):
        """
        Delete cache entry
        
        Args:
            key: Cache key to delete
        """
        # Delete from memory cache
        self.memory_cache.delete(key)
        
        # Delete from Redis cache
        if self.redis_available:
            try:
                self.redis_client.delete(key)
                with self.stats_lock:
                    self.stats['deletes'] += 1
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}")
        else:
            with self.stats_lock:
                self.stats['deletes'] += 1
    
    def clear(self, pattern: Optional[str] = None):
        """
        Clear cache entries
        
        Args:
            pattern: Pattern to match keys (Redis only)
        """
        # Clear memory cache
        self.memory_cache.clear()
        
        # Clear Redis cache
        if self.redis_available and pattern:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} Redis keys matching pattern: {pattern}")
            except Exception as e:
                logger.warning(f"Redis clear failed: {e}")
        elif self.redis_available:
            try:
                self.redis_client.flushdb()
                logger.info("Cleared all Redis cache")
            except Exception as e:
                logger.warning(f"Redis flush failed: {e}")
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        with self.stats_lock:
            stats = self.stats.copy()
        
        # Calculate hit rate
        total_requests = stats['memory_hits'] + stats['redis_hits'] + stats['misses']
        if total_requests > 0:
            stats['hit_rate'] = (stats['memory_hits'] + stats['redis_hits']) / total_requests
        else:
            stats['hit_rate'] = 0.0
        
        # Add memory cache size
        stats['memory_cache_size'] = self.memory_cache.size()
        
        return stats
    
    def warm_up(self, data: Dict[str, Any], ttl: int = 3600):
        """
        Warm up cache with initial data
        
        Args:
            data: Dictionary of key-value pairs to cache
            ttl: Time to live for cached data
        """
        logger.info(f"Warming up cache with {len(data)} items")
        
        for key, value in data.items():
            self.set(key, value, ttl=ttl)
        
        logger.info("Cache warm-up completed")

def cache_result(prefix: str, ttl: int = 300, use_memory: bool = True):
    """
    Decorator for caching function results
    
    Args:
        prefix: Cache key prefix
        ttl: Time to live (seconds)
        use_memory: Whether to use memory cache
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get cache instance (assume global instance)
            cache = get_global_cache()
            if cache is None:
                return func(*args, **kwargs)
            
            # Generate cache key
            key = cache._generate_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = cache.get(key, use_memory=use_memory)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result, ttl=ttl, use_memory=use_memory)
            
            return result
        return wrapper
    return decorator

# Global cache instance
_global_cache = None

def get_global_cache() -> Optional[PerformanceCache]:
    """Get global cache instance"""
    return _global_cache

def set_global_cache(cache: PerformanceCache):
    """Set global cache instance"""
    global _global_cache
    _global_cache = cache 
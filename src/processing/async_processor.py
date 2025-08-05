"""
Asynchronous Processor

This module is responsible for:
1. Asynchronous message processing
2. Multi-threaded parallel computation
3. Asynchronous I/O operation optimization
4. Task queue management

Performance improvement targets:
- Throughput improvement: 50-80%
- Processing latency reduction: 60-70%
- Resource utilization improvement: 40-60%
"""
import asyncio
import aiohttp
import aiokafka
import json
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from queue import Queue, PriorityQueue
import time
import weakref

logger = logging.getLogger(__name__)

class AsyncMessageProcessor:
    """
    Asynchronous Message Processor
    
    Features:
    - Asynchronous Kafka consumption and production
    - Multi-threaded parallel processing
    - Intelligent task scheduling
    - Backpressure control
    """
    
    def __init__(self,
                 bootstrap_servers: List[str],
                 input_topic: str,
                 output_topic: str,
                 max_workers: int = 8,
                 batch_size: int = 100,
                 max_queue_size: int = 10000):
        """
        Initialize asynchronous processor
        
        Args:
            bootstrap_servers: List of Kafka servers
            input_topic: Input topic
            output_topic: Output topic
            max_workers: Maximum number of worker threads
            batch_size: Batch processing size
            max_queue_size: Maximum queue size
        """
        self.bootstrap_servers = bootstrap_servers
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.max_queue_size = max_queue_size
        
        # Asynchronous components
        self.consumer = None
        self.producer = None
        self.session = None
        
        # Task queues
        self.task_queue = asyncio.Queue(maxsize=max_queue_size)
        self.result_queue = asyncio.Queue(maxsize=max_queue_size)
        
        # Thread pools
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.process_pool = ProcessPoolExecutor(max_workers=max_workers//2)
        
        # Performance monitoring
        self.stats = {
            'messages_processed': 0,
            'messages_per_second': 0,
            'average_processing_time': 0,
            'queue_size': 0,
            'active_workers': 0
        }
        self.stats_lock = threading.Lock()
        
        # Control flags
        self.running = False
        self.shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """Initialize asynchronous components"""
        try:
            # Initialize Kafka consumer
            self.consumer = aiokafka.AIOKafkaConsumer(
                self.input_topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id='async_processor_group',
                auto_offset_reset='latest',
                enable_auto_commit=True,
                auto_commit_interval_ms=1000,
                max_poll_records=self.batch_size
            )
            
            # Initialize Kafka producer
            self.producer = aiokafka.AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                compression_type='snappy',
                batch_size=16384,
                linger_ms=5
            )
            
            # Initialize HTTP session for external API calls
            self.session = aiohttp.ClientSession()
            
            logger.info("Asynchronous components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize async components: {e}")
            raise
    
    async def start(self):
        """Start the asynchronous processor"""
        await self.initialize()
        self.running = True
        
        # Start all components
        tasks = [
            asyncio.create_task(self._message_consumer()),
            asyncio.create_task(self._result_processor()),
            asyncio.create_task(self._stats_monitor())
        ]
        
        # Start worker pool
        await self.start_workers()
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in async processor: {e}")
        finally:
            await self.shutdown()
    
    async def start_workers(self):
        """Start worker coroutines"""
        worker_tasks = []
        for i in range(self.max_workers):
            worker_id = f"worker_{i}"
            task = asyncio.create_task(self._worker(worker_id))
            worker_tasks.append(task)
        
        logger.info(f"Started {self.max_workers} worker coroutines")
    
    async def _message_consumer(self):
        """Consume messages from Kafka and add to task queue"""
        await self.consumer.start()
        
        try:
            async for msg in self.consumer:
                if not self.running:
                    break
                
                try:
                    data = json.loads(msg.value.decode('utf-8'))
                    await self.task_queue.put(data)
                    
                    with self.stats_lock:
                        self.stats['messages_processed'] += 1
                        
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except Exception as e:
            logger.error(f"Error in message consumer: {e}")
        finally:
            await self.consumer.stop()
    
    async def _worker(self, worker_id: str):
        """Worker coroutine"""
        logger.info(f"Starting worker: {worker_id}")
        
        while not self.shutdown_event.is_set():
            try:
                message = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )
                
                # Process message asynchronously
                result = await self._process_message(message)
                
                if result:
                    await self.result_queue.put(result)
                
                self.task_queue.task_done()
                
                with self.stats_lock:
                    self.stats['active_workers'] += 1
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                continue
            finally:
                with self.stats_lock:
                    self.stats['active_workers'] = max(0, self.stats['active_workers'] - 1)
        
        logger.info(f"Worker {worker_id} stopped")
    
    async def _process_message(self, message: Dict) -> Optional[Dict]:
        """
        Process individual message
        
        Args:
            message: Input message data
            
        Returns:
            Processed result or None
        """
        try:
            start_time = time.time()
            
            # Determine message type and process accordingly
            message_type = message.get('type', 'price_data')
            
            if message_type == 'price_data':
                result = await self._process_price_data(message)
            elif message_type == 'alert':
                result = await self._process_alert_data(message)
            else:
                result = await self._process_generic_data(message)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            with self.stats_lock:
                self.stats['average_processing_time'] = (
                    (self.stats['average_processing_time'] + processing_time) / 2
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return None
    
    async def _process_price_data(self, data: Dict) -> Dict:
        """Process price data asynchronously"""
        loop = asyncio.get_event_loop()
        
        # Offload CPU-intensive calculations to thread pool
        technical_indicators = await loop.run_in_executor(
            self.thread_pool,
            self._calculate_technical_indicators,
            data
        )
        
        # Detect anomalies
        anomaly_result = await loop.run_in_executor(
            self.thread_pool,
            self._detect_anomalies,
            data
        )
        
        # Calculate alert priority
        priority = await loop.run_in_executor(
            self.thread_pool,
            self._calculate_alert_priority,
            data
        )
        
        return {
            **data,
            'technical_indicators': technical_indicators,
            'anomaly_detected': anomaly_result['is_anomaly'],
            'anomaly_score': anomaly_result['score'],
            'priority': priority,
            'processed_at': datetime.now().isoformat()
        }
    
    async def _process_alert_data(self, data: Dict) -> Dict:
        """Process alert data asynchronously"""
        # Format alert message
        formatted_alert = await self._format_alert(data)
        
        return {
            **data,
            'formatted_message': formatted_alert,
            'processed_at': datetime.now().isoformat()
        }
    
    async def _process_generic_data(self, data: Dict) -> Dict:
        """Process generic data asynchronously"""
        return {
            **data,
            'processed_at': datetime.now().isoformat()
        }
    
    def _calculate_technical_indicators(self, data: Dict) -> Dict:
        """Calculate technical indicators (CPU-intensive)"""
        price = data.get('price', 0)
        volume = data.get('volume', 0)
        
        # Simulate technical indicator calculations
        return {
            'rsi': 50 + (price % 20),
            'macd': (price % 10) - 5,
            'bollinger_position': (price % 100) / 100,
            'moving_avg_ratio': 1.0 + (price % 10) / 100
        }
    
    def _detect_anomalies(self, data: Dict) -> Dict:
        """Detect anomalies in data (CPU-intensive)"""
        price = data.get('price', 0)
        volume = data.get('volume', 0)
        
        # Simulate anomaly detection
        anomaly_score = (price % 100) / 100
        is_anomaly = anomaly_score > 0.8
        
        return {
            'is_anomaly': is_anomaly,
            'score': anomaly_score,
            'confidence': 0.7 + (anomaly_score * 0.3)
        }
    
    def _calculate_alert_priority(self, data: Dict) -> int:
        """Calculate alert priority (CPU-intensive)"""
        price_change = abs(data.get('price_change_pct', 0))
        
        if price_change > 10:
            return 1  # High priority
        elif price_change > 5:
            return 2  # Medium priority
        else:
            return 3  # Low priority
    
    async def _format_alert(self, data: Dict) -> str:
        """Format alert message"""
        symbol = data.get('symbol', 'UNKNOWN')
        price = data.get('price', 0)
        return f"Alert: {symbol} price anomaly detected at ${price:.2f}"
    
    async def _result_processor(self):
        """Process results and send to output topic"""
        await self.producer.start()
        
        try:
            while not self.shutdown_event.is_set():
                try:
                    result = await asyncio.wait_for(
                        self.result_queue.get(),
                        timeout=1.0
                    )
                    
                    # Send result to Kafka
                    await self.producer.send_and_wait(
                        self.output_topic,
                        json.dumps(result).encode('utf-8')
                    )
                    
                    self.result_queue.task_done()
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error in result processor: {e}")
                    
        except Exception as e:
            logger.error(f"Error in result processor: {e}")
        finally:
            await self.producer.stop()
    
    async def _stats_monitor(self):
        """Monitor and log performance statistics"""
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(10)  # Log stats every 10 seconds
                
                with self.stats_lock:
                    queue_size = self.task_queue.qsize()
                    self.stats['queue_size'] = queue_size
                    
                    # Calculate messages per second
                    current_time = time.time()
                    if hasattr(self, '_last_stats_time'):
                        time_diff = current_time - self._last_stats_time
                        if time_diff > 0:
                            self.stats['messages_per_second'] = (
                                self.stats['messages_processed'] / time_diff
                            )
                    self._last_stats_time = current_time
                
                logger.info(f"Stats: {self.stats}")
                
            except Exception as e:
                logger.error(f"Error in stats monitor: {e}")
    
    async def shutdown(self):
        """Shutdown the processor gracefully"""
        logger.info("Shutting down async processor...")
        self.running = False
        self.shutdown_event.set()
        
        # Close session
        if self.session:
            await self.session.close()
        
        # Shutdown thread pools
        self.thread_pool.shutdown(wait=True)
        self.process_pool.shutdown(wait=True)
        
        logger.info("Async processor shutdown complete")
    
    def get_stats(self) -> Dict:
        """Get current performance statistics"""
        with self.stats_lock:
            return self.stats.copy()

async def main():
    """Main function for running the async processor"""
    processor = AsyncMessageProcessor(
        bootstrap_servers=['localhost:9092'],
        input_topic='crypto_analytics',
        output_topic='crypto_processed_data',
        max_workers=8,
        batch_size=100
    )
    
    await processor.start()

if __name__ == "__main__":
    asyncio.run(main()) 
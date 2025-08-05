"""
Price Anomaly Detector for Cryptocurrency Data

This module is responsible for:
1. Consuming processed price data from Kafka
2. Detecting price anomalies using statistical methods
3. Generating anomaly alerts and sending to downstream
4. Providing configurable anomaly detection algorithms

Component Coordination:
- Upstream: Kafka topic (crypto_analytics) - analysis results from price processor
- Downstream: Kafka topic (crypto_price_anomalies) - anomaly alerts
- Coordination: Kafka consumer-producer pattern for decoupled anomaly detection

Data Flow Analysis:
1. Consume analysis data → Sliding window statistics → Z-score calculation
2. Anomaly detection algorithm → Threshold judgment → Generate alerts
3. Support multiple anomaly detection methods: Z-score, price change percentage, moving average deviation
4. Configurable detection parameters and alert levels

Performance Optimization Strategy:
1. Sliding window: Only keep recent N data points, control memory usage
2. Incremental calculation: Avoid repeated calculation of statistical indicators
3. Batch processing: Process messages in batches to improve throughput
4. Memory management: Clean up expired data in time to avoid memory leaks
5. Algorithm optimization: Use efficient statistical calculation methods

Interface Design:
- Input: Kafka messages (JSON format analysis data)
- Output: Anomaly alerts (JSON format)
- Configuration parameters: window size, Z-score threshold, price change threshold, etc.
- Monitoring metrics: detected anomalies, false positive rate, processing delay, etc.

Anomaly Detection Algorithms:
1. Z-score method: Detect anomalies based on statistical standard deviation
2. Price change percentage: Detect large price fluctuations
3. Moving average deviation: Detect price trend anomalies
4. Combined detection: Combine multiple methods to improve detection accuracy
"""
import numpy as np
from confluent_kafka import Consumer, Producer
import json
from typing import List, Dict, Optional
import logging
from datetime import datetime
import pandas as pd
from scipy import stats

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PriceAnomalyDetector:
    """
    Price Anomaly Detector
    
    Uses multiple statistical methods to detect cryptocurrency price anomalies:
    - Z-score method: Detect anomalies based on statistical standard deviation
    - Price change percentage: Detect large price fluctuations
    - Moving average deviation: Detect price trend anomalies
    - Combined detection: Combine multiple methods to improve accuracy
    
    Design Patterns:
    - Strategy pattern: Configurable anomaly detection algorithms
    - Observer pattern: Automatically trigger detection when data updates
    - Factory pattern: Create different detectors based on configuration
    
    Performance Features:
    - Sliding window: Control memory usage
    - Incremental calculation: Avoid repeated calculations
    - Batch processing: Improve throughput
    - Configurable parameters: Adapt to different detection requirements
    """
    
    def __init__(
        self,
        bootstrap_servers: List[str],
        input_topic: str,
        output_topic: str,
        window_size: int = 60,
        z_score_threshold: float = 3.0
    ):
        """
        Initialize the Price Anomaly Detector.
        
        Args:
            bootstrap_servers: List of Kafka broker addresses
            input_topic: Topic to consume processed price data from
            output_topic: Topic to publish anomaly alerts to
            window_size: Size of the rolling window for calculations (in minutes)
            z_score_threshold: Z-score threshold for anomaly detection
        """
        # Create Kafka consumer
        consumer_config = {
            'bootstrap.servers': ','.join(bootstrap_servers),
            'group.id': 'price_anomaly_detector',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True,
            'auto.commit.interval.ms': 1000,
            'session.timeout.ms': 30000,
            'max.poll.records': 100
        }
        
        self.consumer = Consumer(consumer_config)
        self.consumer.subscribe([input_topic])
        
        # Create Kafka producer
        producer_config = {
            'bootstrap.servers': ','.join(bootstrap_servers),
            'compression.type': 'snappy',
            'batch.size': 16384,
            'linger.ms': 5
        }
        
        self.producer = Producer(producer_config)
        
        # Configuration
        self.output_topic = output_topic
        self.window_size = window_size
        self.z_score_threshold = z_score_threshold
        
        # Data storage
        self.price_history: Dict[str, List[float]] = {}
        self.volume_history: Dict[str, List[float]] = {}
        self.moving_avg_history: Dict[str, List[float]] = {}
        
        # Performance monitoring
        self.total_messages = 0
        self.total_anomalies = 0
        self.false_positives = 0
        self.detection_accuracy = 0.0

    def calculate_z_score(self, values: List[float]) -> Optional[float]:
        """
        Calculate z-score for the latest value.
        
        Args:
            values: List of historical values
            
        Returns:
            Z-score value or None if insufficient data
        """
        if len(values) < 2:
            return None
        
        recent_values = values[-self.window_size:]
        if len(recent_values) < 2:
            return None
            
        mean = np.mean(recent_values[:-1])
        std = np.std(recent_values[:-1])
        
        if std == 0:
            return 0.0
            
        return (recent_values[-1] - mean) / std

    def detect_anomalies(self, data: Dict) -> Optional[Dict]:
        """
        Detect price anomalies using multiple methods.
        
        Args:
            data: Input data containing price and volume information
            
        Returns:
            Anomaly alert dictionary or None if no anomaly detected
        """
        symbol = data['symbol']
        current_price = data['price']
        volume = data.get('volume', 0.0)
        
        # Initialize history for new symbols
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.volume_history[symbol] = []
            self.moving_avg_history[symbol] = []
        
        # Update history
        self.price_history[symbol].append(current_price)
        self.volume_history[symbol].append(volume)
        
        # Keep only window_size latest values
        self.price_history[symbol] = self.price_history[symbol][-self.window_size:]
        self.volume_history[symbol] = self.volume_history[symbol][-self.window_size:]
        
        # Calculate moving average
        if len(self.price_history[symbol]) >= 20:
            moving_avg = np.mean(self.price_history[symbol][-20:])
            self.moving_avg_history[symbol].append(moving_avg)
            self.moving_avg_history[symbol] = self.moving_avg_history[symbol][-self.window_size:]
        else:
            moving_avg = current_price
        
        # Multi-dimensional anomaly detection
        anomaly_score = 0
        anomaly_reasons = []
        
        # 1. Z-score detection
        z_score = self.calculate_z_score(self.price_history[symbol])
        if z_score is not None and abs(z_score) > self.z_score_threshold:
            anomaly_score += 2
            anomaly_reasons.append(f"Z-score: {z_score:.2f}")
        
        # 2. Price change detection
        if len(self.price_history[symbol]) >= 2:
            price_change_pct = abs((current_price - self.price_history[symbol][-2]) / self.price_history[symbol][-2]) * 100
            if price_change_pct > 3.0:  # 3% threshold
                anomaly_score += 2
                anomaly_reasons.append(f"Price change: {price_change_pct:.2f}%")
        
        # 3. Volume anomaly detection
        if len(self.volume_history[symbol]) >= 2:
            volume_change_pct = abs((volume - self.volume_history[symbol][-2]) / self.volume_history[symbol][-2]) * 100
            if volume_change_pct > 50.0:  # 50% threshold
                anomaly_score += 1
                anomaly_reasons.append(f"Volume change: {volume_change_pct:.2f}%")
        
        # 4. Moving average deviation
        if len(self.moving_avg_history[symbol]) >= 1:
            ma_deviation = abs((current_price - moving_avg) / moving_avg) * 100
            if ma_deviation > 10.0:  # 10% threshold
                anomaly_score += 1
                anomaly_reasons.append(f"MA deviation: {ma_deviation:.2f}%")
        
        # 5. Volatility detection
        if len(self.price_history[symbol]) >= 10:
            returns = np.diff(self.price_history[symbol][-10:]) / self.price_history[symbol][-11:-1]
            volatility = np.std(returns) * 100
            if volatility > 15.0:  # 15% threshold
                anomaly_score += 1
                anomaly_reasons.append(f"High volatility: {volatility:.2f}%")
        
        # Determine if anomaly detected
        if anomaly_score >= 2:
            severity = self._determine_severity(z_score or 0, price_change_pct if 'price_change_pct' in locals() else 0, ma_deviation if 'ma_deviation' in locals() else 0)
            confidence = self._calculate_confidence(z_score or 0, price_change_pct if 'price_change_pct' in locals() else 0, ma_deviation if 'ma_deviation' in locals() else 0)
            
            return {
                'symbol': symbol,
                'timestamp': data.get('timestamp', datetime.now().isoformat()),
                'current_price': current_price,
                'volume': volume,
                'anomaly_score': anomaly_score,
                'reasons': anomaly_reasons,
                'severity': severity,
                'confidence': confidence,
                'z_score': z_score,
                'price_change_pct': price_change_pct if 'price_change_pct' in locals() else 0,
                'volume_change_pct': volume_change_pct if 'volume_change_pct' in locals() else 0,
                'ma_deviation': ma_deviation if 'ma_deviation' in locals() else 0,
                'volatility': volatility if 'volatility' in locals() else 0,
                'alert_type': 'price_anomaly'
            }
        
        return None

    def _determine_severity(self, z_score: float, price_change_pct: float, ma_deviation: float) -> str:
        """
        Determine anomaly severity based on multiple factors.
        
        Args:
            z_score: Z-score value
            price_change_pct: Price change percentage
            ma_deviation: Moving average deviation
            
        Returns:
            Severity level: 'low', 'medium', 'high', 'critical'
        """
        severity_score = 0
        
        if abs(z_score) > 4.0:
            severity_score += 3
        elif abs(z_score) > 3.0:
            severity_score += 2
        elif abs(z_score) > 2.0:
            severity_score += 1
        
        if price_change_pct > 10.0:
            severity_score += 3
        elif price_change_pct > 5.0:
            severity_score += 2
        elif price_change_pct > 3.0:
            severity_score += 1
        
        if ma_deviation > 20.0:
            severity_score += 2
        elif ma_deviation > 10.0:
            severity_score += 1
        
        if severity_score >= 6:
            return 'critical'
        elif severity_score >= 4:
            return 'high'
        elif severity_score >= 2:
            return 'medium'
        else:
            return 'low'

    def _calculate_confidence(self, z_score: float, price_change_pct: float, ma_deviation: float) -> float:
        """
        Calculate confidence level for anomaly detection.
        
        Args:
            z_score: Z-score value
            price_change_pct: Price change percentage
            ma_deviation: Moving average deviation
            
        Returns:
            Confidence level between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence
        
        # Z-score contribution
        if abs(z_score) > 4.0:
            confidence += 0.3
        elif abs(z_score) > 3.0:
            confidence += 0.2
        elif abs(z_score) > 2.0:
            confidence += 0.1
        
        # Price change contribution
        if price_change_pct > 10.0:
            confidence += 0.2
        elif price_change_pct > 5.0:
            confidence += 0.15
        elif price_change_pct > 3.0:
            confidence += 0.1
        
        # Moving average deviation contribution
        if ma_deviation > 20.0:
            confidence += 0.1
        elif ma_deviation > 10.0:
            confidence += 0.05
        
        return min(confidence, 1.0)

    def run(self):
        """Run the anomaly detection process."""
        logger.info("Starting anomaly detection process...")
        
        try:
            while True:
                msg = self.consumer.poll(1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
                
                try:
                    data = json.loads(msg.value().decode('utf-8'))
                    self.total_messages += 1
                    
                    anomaly = self.detect_anomalies(data)
                    if anomaly:
                        logger.info(f"Anomaly detected for {anomaly['symbol']}: {anomaly}")
                        self.producer.produce(
                            self.output_topic,
                            json.dumps(anomaly).encode('utf-8'),
                            callback=self._delivery_report
                        )
                        self.producer.flush()
                        self.total_anomalies += 1
                    
                    # Print stats every 100 messages
                    if self.total_messages % 100 == 0:
                        self._print_stats()
                        
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Shutting down anomaly detector...")
        finally:
            self.consumer.close()
            self.producer.flush()

    def _delivery_report(self, err, msg):
        """Handle delivery reports from Kafka producer."""
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def _print_stats(self):
        """Print performance statistics."""
        logger.info(f"Processed {self.total_messages} messages, detected {self.total_anomalies} anomalies")

def main():
    """Main function for running the anomaly detector."""
    detector = PriceAnomalyDetector(
        bootstrap_servers=['localhost:9092'],
        input_topic='crypto_analytics',
        output_topic='crypto_price_anomalies',
        window_size=60,
        z_score_threshold=3.0
    )
    detector.run()

if __name__ == "__main__":
    main()
import numpy as np
from kafka import KafkaConsumer, KafkaProducer
import json
from typing import List, Dict, Optional
import logging
from datetime import datetime
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedPriceAnomalyDetector:
    def __init__(
        self,
        bootstrap_servers: List[str],
        input_topic: str,
        output_topic: str,
        window_size: int = 60,
        z_score_threshold: float = 3.0,
        use_ml_detection: bool = True,
        ensemble_methods: bool = True
    ):
        """
        Initialize the Enhanced Price Anomaly Detector.
        
        Args:
            bootstrap_servers: List of Kafka broker addresses
            input_topic: Topic to consume processed price data from
            output_topic: Topic to publish anomaly alerts to
            window_size: Size of the rolling window for calculations (in minutes)
            z_score_threshold: Z-score threshold for anomaly detection
            use_ml_detection: Whether to use machine learning detection
            ensemble_methods: Whether to use ensemble methods
        """
        self.consumer = KafkaConsumer(
            input_topic,
            bootstrap_servers=bootstrap_servers,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            group_id='enhanced_price_anomaly_detector',
            max_poll_records=100,
            session_timeout_ms=30000
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            compression_type='snappy',
            batch_size=16384,
            linger_ms=5
        )
        
        self.output_topic = output_topic
        self.window_size = window_size
        self.z_score_threshold = z_score_threshold
        self.use_ml_detection = use_ml_detection
        self.ensemble_methods = ensemble_methods
        
        # 数据存储
        self.price_history: Dict[str, List[float]] = {}
        self.moving_avg_history: Dict[str, List[float]] = {}
        self.volume_history: Dict[str, List[float]] = {}
        
        # ML模型
        if self.use_ml_detection:
            self.isolation_forest = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=100
            )
            self.scaler = StandardScaler()
            self.ml_trained = False
        
        # 性能监控
        self.total_messages = 0
        self.total_anomalies = 0
        self.false_positives = 0
        self.detection_accuracy = 0.0

    def calculate_z_score(self, values: List[float]) -> Optional[float]:
        """Calculate z-score for the latest value."""
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
        Detect price anomalies using enhanced methods.
        
        Uses ensemble of statistical and ML methods for better accuracy.
        """
        symbol = data['symbol']
        current_price = data['price']
        moving_avg = data.get('moving_avg', current_price)
        price_change_pct = data.get('price_change_pct', 0.0)
        volume = data.get('volume', 0.0)
        
        # Initialize history for new symbols
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.moving_avg_history[symbol] = []
            self.volume_history[symbol] = []
        
        # Update history
        self.price_history[symbol].append(current_price)
        self.moving_avg_history[symbol].append(moving_avg)
        self.volume_history[symbol].append(volume)
        
        # Keep only window_size latest values
        self.price_history[symbol] = self.price_history[symbol][-self.window_size:]
        self.moving_avg_history[symbol] = self.moving_avg_history[symbol][-self.window_size:]
        self.volume_history[symbol] = self.volume_history[symbol][-self.window_size:]
        
        # 使用集成方法检测异常
        if self.ensemble_methods:
            anomaly_result = self._ensemble_anomaly_detection(symbol, data)
        else:
            anomaly_result = self._statistical_anomaly_detection(symbol, data)
        
        return anomaly_result
    
    def _ensemble_anomaly_detection(self, symbol: str, data: Dict) -> Optional[Dict]:
        """集成异常检测方法"""
        # 1. 统计方法检测
        statistical_result = self._statistical_anomaly_detection(symbol, data)
        
        # 2. ML方法检测
        ml_result = None
        if self.use_ml_detection and self.ml_trained:
            ml_result = self._ml_anomaly_detection(symbol, data)
        
        # 3. 集成决策
        if statistical_result and ml_result:
            # 两种方法都检测到异常，提高置信度
            confidence = 0.9
            severity = 'critical'
        elif statistical_result or ml_result:
            # 只有一种方法检测到异常
            confidence = 0.7
            severity = 'high'
            result = statistical_result or ml_result
        else:
            return None
        
        # 返回增强的异常结果
        return {
            'symbol': symbol,
            'timestamp': data['timestamp'],
            'current_price': data['price'],
            'moving_average': data.get('moving_avg', data['price']),
            'price_change_pct': data.get('price_change_pct', 0.0),
            'confidence': confidence,
            'severity': severity,
            'detection_methods': {
                'statistical': statistical_result is not None,
                'ml': ml_result is not None
            },
            'anomaly_type': 'ensemble_detection'
        }
    
    def _statistical_anomaly_detection(self, symbol: str, data: Dict) -> Optional[Dict]:
        """统计方法异常检测"""
        current_price = data['price']
        price_change_pct = data.get('price_change_pct', 0.0)
        
        # Calculate z-scores
        price_z_score = self.calculate_z_score(self.price_history[symbol])
        
        if price_z_score is None:
            return None
            
        # 计算移动平均偏离
        moving_avg_deviation = 0.0
        if len(self.moving_avg_history[symbol]) > 1:
            moving_avg = self.moving_avg_history[symbol][-1]
            if moving_avg > 0:
                moving_avg_deviation = (current_price - moving_avg) / moving_avg * 100
        
        # 计算波动率
        volatility = self._calculate_volatility(self.price_history[symbol])
        
        # 多维度异常检测
        anomaly_score = 0
        anomaly_reasons = []
        
        # Z-score检测
        if abs(price_z_score) > self.z_score_threshold:
            anomaly_score += 2
            anomaly_reasons.append(f"Z-score: {price_z_score:.2f}")
        
        # 价格变化检测
        if abs(price_change_pct) > 5.0:
            anomaly_score += 2
            anomaly_reasons.append(f"Price change: {price_change_pct:.2f}%")
        
        # 移动平均偏离检测
        if abs(moving_avg_deviation) > 10.0:
            anomaly_score += 1
            anomaly_reasons.append(f"MA deviation: {moving_avg_deviation:.2f}%")
        
        # 波动率检测
        if volatility > 20.0:
            anomaly_score += 1
            anomaly_reasons.append(f"High volatility: {volatility:.2f}%")
        
        # 判断是否为异常
        if anomaly_score >= 2:
            severity = 'critical' if anomaly_score >= 4 else 'high' if anomaly_score >= 3 else 'medium'
            return {
                'symbol': symbol,
                'timestamp': data['timestamp'],
                'current_price': current_price,
                'price_change_pct': price_change_pct,
                'z_score': price_z_score,
                'moving_avg_deviation': moving_avg_deviation,
                'volatility': volatility,
                'anomaly_score': anomaly_score,
                'reasons': anomaly_reasons,
                'severity': severity,
                'anomaly_type': 'statistical_detection'
            }
        
        return None
    
    def _ml_anomaly_detection(self, symbol: str, data: Dict) -> Optional[Dict]:
        """机器学习异常检测"""
        try:
            # 准备特征
            features = self._prepare_ml_features(symbol, data)
            
            if len(features) == 0:
                return None
            
            # 使用Isolation Forest检测异常
            features_array = np.array(features).reshape(1, -1)
            anomaly_score = self.isolation_forest.decision_function(features_array)[0]
            is_anomaly = self.isolation_forest.predict(features_array)[0] == -1
            
            if is_anomaly:
                return {
                    'symbol': symbol,
                    'timestamp': data['timestamp'],
                    'current_price': data['price'],
                    'ml_anomaly_score': anomaly_score,
                    'severity': 'high' if anomaly_score < -0.5 else 'medium',
                    'anomaly_type': 'ml_detection'
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"ML anomaly detection failed: {e}")
            return None
    
    def _prepare_ml_features(self, symbol: str, data: Dict) -> List[float]:
        """准备ML特征"""
        if len(self.price_history[symbol]) < 10:
            return []
        
        features = []
        
        # 价格特征
        prices = self.price_history[symbol][-10:]
        features.extend([
            np.mean(prices),
            np.std(prices),
            prices[-1] / np.mean(prices) - 1,  # 价格偏离度
            (prices[-1] - prices[0]) / prices[0]  # 价格变化率
        ])
        
        # 技术指标
        if len(prices) >= 20:
            ma_20 = np.mean(prices[-20:])
            features.append(prices[-1] / ma_20 - 1)
        else:
            features.append(0.0)
        
        # 波动率特征
        if len(prices) >= 2:
            returns = np.diff(prices) / prices[:-1]
            features.append(np.std(returns))
        else:
            features.append(0.0)
        
        # 成交量特征
        if symbol in self.volume_history and len(self.volume_history[symbol]) >= 5:
            volumes = self.volume_history[symbol][-5:]
            features.append(np.mean(volumes))
            features.append(volumes[-1] / np.mean(volumes) - 1)
        else:
            features.extend([0.0, 0.0])
        
        return features
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """计算波动率"""
        if len(prices) < 2:
            return 0.0
        
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                returns.append((prices[i] - prices[i-1]) / prices[i-1])
        
        if len(returns) == 0:
            return 0.0
        
        return np.std(returns) * 100  # 转换为百分比

    def run(self):
        """Run the anomaly detection process."""
        logger.info("Starting anomaly detection process...")
        
        try:
            for message in self.consumer:
                data = message.value
                
                anomaly = self.detect_anomalies(data)
                if anomaly:
                    logger.info(f"Anomaly detected for {anomaly['symbol']}: {anomaly}")
                    self.producer.send(self.output_topic, value=anomaly)
                    self.producer.flush()
                    
        except Exception as e:
            logger.error(f"Error in anomaly detection: {str(e)}")
            raise

if __name__ == "__main__":
    # Example usage
    detector = PriceAnomalyDetector(
        bootstrap_servers=['localhost:9092'],
        # input_topic='processed_crypto_prices',
        input_topic='crypto_analytics',
        output_topic='crypto_price_anomalies',
        window_size=60,  # 1 hour window
        z_score_threshold=3.0
    )
    detector.run() 
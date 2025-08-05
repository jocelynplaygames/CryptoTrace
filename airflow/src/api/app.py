"""
基于FastAPI的加密货币数据服务API。
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kafka import KafkaConsumer
import pandas as pd
import logging

app = FastAPI(
    title="Crypto Price API",
    description="API for accessing cryptocurrency price data and analytics",
    version="1.0.0"
)

# 启用CORS，允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class PriceData(BaseModel):
    """
    价格数据模型。
    """
    symbol: str
    price: float
    timestamp: datetime
    
class AnalyticsData(BaseModel):
    """
    分析数据模型。
    """
    symbol: str
    avg_price: float
    min_price: float
    max_price: float
    timestamp: datetime
    
class AlertData(BaseModel):
    """
    告警数据模型。
    """
    type: str
    symbol: str
    price: float
    timestamp: datetime
    threshold: Optional[float] = None
    direction: Optional[str] = None
    previous_price: Optional[float] = None
    change_percent: Optional[float] = None

# 数据访问函数
def get_price_data(symbol: str, start_time: datetime, end_time: datetime) -> List[Dict]:
    """
    获取指定币种在时间区间内的历史价格数据。
    """
    # Construct data directory path
    base_dir = "data/raw"
    symbol_dir = f"{base_dir}/{symbol.lower()}"
    
    if not os.path.exists(symbol_dir):
        return []
    
    # Find relevant data files
    data = []
    current_time = start_time
    while current_time <= end_time:
        # Construct path for this timestamp
        path = f"{symbol_dir}/{current_time.year}/{current_time.month:02d}/{current_time.day:02d}/{current_time.hour:02d}"
        if os.path.exists(path):
            # Read all files in this directory
            for filename in os.listdir(path):
                if not filename.endswith('.json'):
                    continue
                    
                file_time = datetime.strptime(filename.split('.')[0], "%Y%m%d_%H%M%S_%f")
                if start_time <= file_time <= end_time:
                    with open(os.path.join(path, filename), 'r') as f:
                        try:
                            file_data = json.load(f)
                            data.append(file_data)
                        except json.JSONDecodeError:
                            continue
                            
        current_time += timedelta(hours=1)
    
    return data

def get_analytics_data(symbol: str, start_time: datetime, end_time: datetime) -> List[Dict]:
    """
    获取指定币种在时间区间内的历史分析数据。
    """
    # Similar to get_price_data but for analytics
    # For now, we'll calculate analytics from price data
    prices = get_price_data(symbol, start_time, end_time)
    if not prices:
        return []
        
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(prices)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Resample to 1-minute intervals and calculate analytics
    resampled = df.resample('1Min').agg({
        'price': ['mean', 'min', 'max']
    }).dropna()
    
    # Format results
    analytics = []
    for timestamp, row in resampled.iterrows():
        analytics.append({
            'symbol': symbol,
            'avg_price': row[('price', 'mean')],
            'min_price': row[('price', 'min')],
            'max_price': row[('price', 'max')],
            'timestamp': timestamp
        })
    
    return analytics

def get_alerts(symbol: Optional[str] = None, alert_type: Optional[str] = None,
               start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Dict]:
    """
    获取历史告警信息。
    """
    # Read alerts from storage
    # For now, we'll return a sample alert
    return [{
        'type': 'threshold',
        'symbol': 'btcusdt',
        'price': 100000.0,
        'threshold': 100000.0,
        'direction': 'above',
        'timestamp': datetime.now()
    }]

# API 路由
@app.get("/")
async def root():
    """
    API根路由，返回服务信息。
    """
    return {"message": "Crypto Price API v1.0.0"}

@app.get("/prices/{symbol}", response_model=List[PriceData])
async def get_prices(
    symbol: str,
    start_time: datetime = Query(default=None),
    end_time: datetime = Query(default=None)
):
    """
    获取指定币种的历史价格数据。
    """
    # Default to last hour if no time range specified
    if not end_time:
        end_time = datetime.now()
    if not start_time:
        start_time = end_time - timedelta(hours=1)
        
    data = get_price_data(symbol, start_time, end_time)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        
    return data

@app.get("/analytics/{symbol}", response_model=List[AnalyticsData])
async def get_analytics(
    symbol: str,
    start_time: datetime = Query(default=None),
    end_time: datetime = Query(default=None)
):
    """
    获取指定币种的历史分析数据。
    """
    # Default to last hour if no time range specified
    if not end_time:
        end_time = datetime.now()
    if not start_time:
        start_time = end_time - timedelta(hours=1)
        
    data = get_analytics_data(symbol, start_time, end_time)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        
    return data

@app.get("/alerts", response_model=List[AlertData])
async def get_alert_history(
    symbol: Optional[str] = None,
    alert_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """
    获取历史告警信息。
    """
    alerts = get_alerts(symbol, alert_type, start_time, end_time)
    if not alerts:
        raise HTTPException(status_code=404, detail="No alerts found")
        
    return alerts

# WebSocket接口用于实时推送价格数据
@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket):
    """
    实时推送指定币种的价格数据。
    """
    await websocket.accept()
    
    try:
        # Initialize Kafka consumer
        consumer = KafkaConsumer(
            f'crypto_prices.{websocket.path_params["symbol"].lower()}',
            bootstrap_servers='localhost:9092',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest'
        )
        
        # Stream messages to WebSocket
        for message in consumer:
            await websocket.send_json(message.value)
            
    except Exception as e:
        await websocket.close()
    finally:
        consumer.close() 

def main():
    """Main function for running the FastAPI server in Airflow environment."""
    import uvicorn
    import os
    
    # 获取配置
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))
    
    try:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.info(f"Starting FastAPI server on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        logging.basicConfig(level=logging.ERROR)
        logger = logging.getLogger(__name__)
        logger.error(f"Error starting API server: {e}")
        raise

if __name__ == "__main__":
    main() 
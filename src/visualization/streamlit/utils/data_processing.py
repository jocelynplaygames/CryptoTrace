"""Data processing utilities for the Streamlit app."""

import pandas as pd
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, timedelta
from src.visualization.streamlit.config.constants import TIME_RANGES, RESAMPLE_INTERVALS

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.append(str(project_root))

try:
    from src.storage.time_series.price_store import PriceStore
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False

@st.cache_data
def load_data():
    """Load and preprocess the cryptocurrency data."""
    try:
        with st.spinner('Loading data...'):
            # 优先尝试从存储系统加载数据
            if STORAGE_AVAILABLE:
                try:
                    # 尝试从存储系统加载分析数据
                    storage_path = project_root / "data" / "prices"
                    price_store = PriceStore(storage_path)
                    
                    # 获取最近24小时的分析数据
                    end_time = datetime.now()
                    start_time = end_time - timedelta(hours=24)
                    
                    # 支持的加密货币符号
                    symbols = ['btc', 'eth', 'sol', 'ada']
                    all_data = []
                    
                    for symbol in symbols:
                        try:
                            analytics_df = price_store.get_analytics_data(
                                symbol=symbol,
                                start_time=start_time,
                                end_time=end_time,
                                as_dataframe=True
                            )
                            if not analytics_df.empty:
                                all_data.append(analytics_df)
                        except Exception as e:
                            st.warning(f"无法加载 {symbol} 的分析数据: {e}")
                    
                    if all_data:
                        df = pd.concat(all_data, ignore_index=True)
                        st.success(f"从存储系统加载了 {len(df)} 条分析数据记录")
                        return df
                    else:
                        st.warning("存储系统中没有找到分析数据，尝试加载CSV文件")
                        
                except Exception as e:
                    st.warning(f"无法从存储系统加载数据: {e}")
            
            # 回退到CSV文件
            df = pd.read_csv('tableau/data/crypto_prices_20241208_215932.csv')
            
            # Verify required columns exist
            required_columns = ['symbol', 'price', 'timestamp', 'volume_24h']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"Missing required columns: {', '.join(missing_columns)}")
                st.stop()
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
            
            return df
    except FileNotFoundError:
        st.error("Data file not found. Please check the file path.")
        st.stop()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.stop()

def process_data(df, symbol, time_range, interval):
    """Process and filter the data based on selected parameters."""
    try:
        # Filter by symbol
        df = df[df['symbol'] == symbol].copy()
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        # Apply time range filter
        if time_range != 'All Data':
            hours = int(TIME_RANGES[time_range].replace('H', ''))
            last_timestamp = df['timestamp'].max()
            df = df[df['timestamp'] >= last_timestamp - pd.Timedelta(hours=hours)]
        
        # Resample data
        df = df.set_index('timestamp')
        resampled = df.resample(RESAMPLE_INTERVALS[interval]).agg({
            'price': 'last',
            'volume_24h': 'sum'
        }).reset_index()
        
        # Forward fill missing values
        resampled = resampled.fillna(method='ffill')
        
        return resampled
    except Exception as e:
        st.error(f"Error processing data: {str(e)}")
        return pd.DataFrame()

def calculate_statistics(df):
    """Calculate various statistics from the data."""
    try:
        if df.empty:
            raise ValueError("No data available for statistics calculation")
            
        stats = {
            'current_price': df['price'].iloc[-1],
            'min_price': df['price'].min(),
            'max_price': df['price'].max(),
            'avg_price': df['price'].mean(),
            'std_dev': df['price'].std(),
            'price_change': df['price'].iloc[-1] - df['price'].iloc[0],
            'avg_volume': df['volume_24h'].mean() if 'volume_24h' in df.columns else 0,
            'skewness': df['price'].skew(),
            'kurtosis': df['price'].kurtosis()
        }
        
        # Calculate derived statistics
        stats['price_change_pct'] = (stats['price_change'] / df['price'].iloc[0]) * 100
        stats['price_range'] = stats['max_price'] - stats['min_price']
        stats['price_volatility'] = (stats['std_dev'] / stats['avg_price']) * 100
        
        # 处理24小时价格变化
        if 'price_change_24h' in df.columns:
            # 如果有24小时价格变化数据，使用最新的值
            stats['price_change_24h'] = df['price_change_24h'].iloc[-1]
        else:
            # 如果没有，计算为0
            stats['price_change_24h'] = 0.0
        
        return stats
    except Exception as e:
        st.error(f"Error calculating statistics: {str(e)}")
        return {k: 0 for k in ['current_price', 'min_price', 'max_price', 'avg_price', 
                              'std_dev', 'price_change', 'avg_volume', 'skewness', 
                              'kurtosis', 'price_change_pct', 'price_range', 'price_volatility',
                              'price_change_24h']} 
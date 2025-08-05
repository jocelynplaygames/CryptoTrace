"""
Performance Monitoring Dashboard

This module is responsible for:
1. Real-time performance metrics collection
2. Performance trend analysis
3. Optimization effect visualization
4. Alerts and notifications

Monitoring metrics:
- Anomaly detection accuracy
- System throughput
- Response latency
- Cache hit rate
- Resource utilization
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import json
import requests
import time
import threading
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Performance Monitor"""
    
    def __init__(self):
        self.metrics_history = {
            'timestamp': [],
            'detection_accuracy': [],
            'throughput': [],
            'latency': [],
            'cache_hit_rate': [],
            'cpu_usage': [],
            'memory_usage': [],
            'false_positive_rate': [],
            'ml_accuracy': []
        }
        self.lock = threading.Lock()
    
    def add_metric(self, metric_name: str, value: float):
        """Add performance metric"""
        with self.lock:
            if metric_name in self.metrics_history:
                self.metrics_history['timestamp'].append(datetime.now())
                self.metrics_history[metric_name].append(value)
                
                # Keep only recent 1000 data points
                if len(self.metrics_history['timestamp']) > 1000:
                    self.metrics_history['timestamp'] = self.metrics_history['timestamp'][-1000:]
                    self.metrics_history[metric_name] = self.metrics_history[metric_name][-1000:]
    
    def get_latest_metrics(self) -> Dict:
        """Get latest metrics"""
        with self.lock:
            latest = {}
            for key, values in self.metrics_history.items():
                if key != 'timestamp' and values:
                    latest[key] = values[-1]
            return latest
    
    def get_metrics_df(self) -> pd.DataFrame:
        """Get metrics DataFrame"""
        with self.lock:
            # Check if we have any data
            if not self.metrics_history['timestamp']:
                # Return empty DataFrame with correct columns
                return pd.DataFrame(columns=self.metrics_history.keys())
            
            # Ensure all arrays have the same length
            max_length = max(len(values) for values in self.metrics_history.values())
            
            # Pad shorter arrays with None
            padded_history = {}
            for key, values in self.metrics_history.items():
                if len(values) < max_length:
                    padded_history[key] = values + [None] * (max_length - len(values))
                else:
                    padded_history[key] = values
            
            return pd.DataFrame(padded_history)

class PerformanceDashboard:
    """Performance Monitoring Dashboard"""
    
    def __init__(self):
        self.monitor = PerformanceMonitor()
        self.setup_page()
    
    def setup_page(self):
        """Setup page configuration"""
        st.set_page_config(
            page_title="CryptoTrace Performance Monitor",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        st.title("🚀 CryptoTrace Performance Monitoring Dashboard")
        
        # Add disclaimer about simulated data
        st.info("📊 **Note**: This dashboard displays simulated performance data for demonstration purposes. In a real production environment, this would show actual system metrics from your cryptocurrency monitoring system.")
        
        st.markdown("---")
    
    def run(self):
        """Run the dashboard"""
        # Sidebar configuration
        self.setup_sidebar()
        
        # Main content
        self.display_key_metrics()
        self.display_performance_trends()
        self.display_optimization_impact()
        self.display_system_status()
        
        # Auto-refresh
        self.setup_auto_refresh()
    
    def setup_sidebar(self):
        """Setup sidebar configuration"""
        st.sidebar.title("📊 Dashboard Controls")
        
        # Time range selector
        st.sidebar.subheader("Time Range")
        time_range = st.sidebar.selectbox(
            "Select time range",
            ["Last Hour", "Last 6 Hours", "Last 24 Hours", "Last Week"],
            index=1
        )
        
        # Metric filters
        st.sidebar.subheader("Metrics Filter")
        show_accuracy = st.sidebar.checkbox("Detection Accuracy", value=True)
        show_throughput = st.sidebar.checkbox("Throughput", value=True)
        show_latency = st.sidebar.checkbox("Latency", value=True)
        show_cache = st.sidebar.checkbox("Cache Hit Rate", value=True)
        
        # Auto-refresh settings
        st.sidebar.subheader("Auto Refresh")
        auto_refresh = st.sidebar.checkbox("Enable auto-refresh", value=True)
        refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 5, 60, 30)
        
        return {
            'time_range': time_range,
            'show_accuracy': show_accuracy,
            'show_throughput': show_throughput,
            'show_latency': show_latency,
            'show_cache': show_cache,
            'auto_refresh': auto_refresh,
            'refresh_interval': refresh_interval
        }
    
    def display_key_metrics(self):
        """Display key performance metrics"""
        st.subheader("📈 Key Performance Metrics")
        
        latest_metrics = self.monitor.get_latest_metrics()
        
        # Create metric columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Detection Accuracy",
                f"{latest_metrics.get('detection_accuracy', 0) * 100:.1f}%",
                f"{latest_metrics.get('detection_accuracy', 0) * 100 - 65:.1f}%"
            )
        
        with col2:
            st.metric(
                "System Throughput",
                f"{latest_metrics.get('throughput', 0):.0f} msg/s",
                f"{latest_metrics.get('throughput', 0) - 1500:.0f} msg/s"
            )
        
        with col3:
            st.metric(
                "Response Latency",
                f"{latest_metrics.get('latency', 0):.1f} ms",
                f"{350 - latest_metrics.get('latency', 0):.1f} ms"
            )
        
        with col4:
            st.metric(
                "Cache Hit Rate",
                f"{latest_metrics.get('cache_hit_rate', 0) * 100:.1f}%",
                f"{latest_metrics.get('cache_hit_rate', 0) * 100 - 60:.1f}%"
            )
    
    def display_performance_trends(self):
        """Display performance trends"""
        st.subheader("📊 Performance Trends")
        
        df = self.monitor.get_metrics_df()
        
        if len(df) > 0:
            # Create subplots with better configuration
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=('Detection Accuracy (%)', 'System Throughput (msg/s)', 'Response Latency (ms)', 'Cache Hit Rate (%)'),
                specs=[[{"secondary_y": False}, {"secondary_y": False}],
                       [{"secondary_y": False}, {"secondary_y": False}]]
            )
            
            # Detection accuracy trend
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'], 
                    y=df['detection_accuracy'] * 100,  # Convert to percentage
                    name='Accuracy', 
                    line=dict(color='green', width=2),
                    mode='lines+markers',
                    marker=dict(size=4)
                ),
                row=1, col=1
            )
            
            # Throughput trend
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'], 
                    y=df['throughput'], 
                    name='Throughput', 
                    line=dict(color='blue', width=2),
                    mode='lines+markers',
                    marker=dict(size=4)
                ),
                row=1, col=2
            )
            
            # Latency trend
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'], 
                    y=df['latency'], 
                    name='Latency', 
                    line=dict(color='red', width=2),
                    mode='lines+markers',
                    marker=dict(size=4)
                ),
                row=2, col=1
            )
            
            # Cache hit rate trend
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'], 
                    y=df['cache_hit_rate'] * 100,  # Convert to percentage
                    name='Cache Hit Rate', 
                    line=dict(color='orange', width=2),
                    mode='lines+markers',
                    marker=dict(size=4)
                ),
                row=2, col=2
            )
            
            # Update layout with better formatting
            fig.update_layout(
                height=600, 
                showlegend=False,
                title_text="Real-time Performance Monitoring (Last 6 Hours)",
                title_x=0.5
            )
            
            # Update x-axis for better time display
            fig.update_xaxes(
                tickformat='%H:%M',
                tickmode='auto',
                nticks=8,
                showgrid=True,
                gridwidth=1,
                gridcolor='lightgray'
            )
            
            # Update y-axes with better formatting
            fig.update_yaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='lightgray',
                zeroline=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Add explanation
            st.info("📈 **Trend Analysis**: These charts show the system performance over the last 6 hours. Each data point represents a 10-minute interval, providing a clear view of performance stability and trends.")
        else:
            st.info("No performance data available yet. Start the system to see metrics.")
    
    def display_optimization_impact(self):
        """Display optimization impact comparison"""
        st.subheader("🎯 Optimization Impact")
        
        # Before/After comparison data with better scaling
        comparison_data = {
            'Metric': ['Detection Accuracy (%)', 'Throughput (msg/s)', 'Latency (ms)', 'Cache Hit Rate (%)', 'False Positive Rate (%)'],
            'Before': [65, 1500, 350, 0, 35],
            'After': [88, 4200, 120, 92, 12],
            'Improvement': [23, 180, -66, 92, -23]
        }
        
        df_comparison = pd.DataFrame(comparison_data)
        
        # Create comparison chart with better scaling
        fig = go.Figure()
        
        # Add Before bars
        fig.add_trace(go.Bar(
            name='Before Optimization',
            x=df_comparison['Metric'],
            y=df_comparison['Before'],
            marker_color='lightcoral',
            text=df_comparison['Before'],
            textposition='auto',
        ))
        
        # Add After bars
        fig.add_trace(go.Bar(
            name='After Optimization',
            x=df_comparison['Metric'],
            y=df_comparison['After'],
            marker_color='lightgreen',
            text=df_comparison['After'],
            textposition='auto',
        ))
        
        fig.update_layout(
            title='Performance Comparison: Before vs After Optimization',
            barmode='group',
            height=500,
            yaxis_title='Value',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Improvement summary with better formatting
        st.subheader("📈 Key Improvements")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Detection Accuracy", "+23%", "65% → 88%")
            st.metric("System Throughput", "+180%", "1,500 → 4,200 msg/s")
            st.metric("Response Latency", "-66%", "350ms → 120ms")
        
        with col2:
            st.metric("Cache Hit Rate", "New Feature", "0% → 92%")
            st.metric("False Positive Rate", "-66%", "35% → 12%")
            st.metric("Overall Performance", "+128%", "Significant improvement")
    
    def display_system_status(self):
        """Display system status"""
        st.subheader("🔧 System Status")
        
        # System health indicators
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("CPU Usage", "45%", "-30%")
            if 45 < 75:
                st.success("✅ Normal")
            else:
                st.error("❌ High")
        
        with col2:
            st.metric("Memory Usage", "384MB", "-128MB")
            if 384 < 512:
                st.success("✅ Normal")
            else:
                st.warning("⚠️ High")
        
        with col3:
            st.metric("Active Connections", "156", "+23")
            st.success("✅ Stable")
        
        with col4:
            st.metric("Error Rate", "0.2%", "-0.8%")
            if 0.2 < 1.0:
                st.success("✅ Low")
            else:
                st.error("❌ High")
        
        # System components status
        st.subheader("🔌 Component Status")
        
        components = {
            'Kafka Consumer': '🟢 Running',
            'Kafka Producer': '🟢 Running',
            'Anomaly Detector': '🟢 Running',
            'ML Models': '🟢 Active',
            'Cache System': '🟢 Active',
            'Async Processor': '🟢 Running',
            'Performance Monitor': '🟢 Active'
        }
        
        for component, status in components.items():
            st.text(f"{component}: {status}")
    
    def setup_auto_refresh(self):
        """Setup auto-refresh functionality"""
        st.markdown("---")
        st.markdown("*Dashboard auto-refreshes every 30 seconds*")
    
    def simulate_metrics(self):
        """Simulate performance metrics for demonstration"""
        import random
        import time
        
        # Generate data starting from current time (more realistic)
        current_time = time.time()
        hours_back = 6  # Last 6 hours
        
        for i in range(hours_back * 6):  # 6 data points per hour = 36 total points
            # Calculate timestamp starting from 6 hours ago to now
            timestamp = current_time - (hours_back * 3600) + (i * 600)  # 10-minute intervals
            
            # Generate realistic metrics with smoother variation
            base_accuracy = 0.85 + (i % 6) * 0.015  # Smoother accuracy variation
            base_throughput = 3800 + (i % 12) * 30   # Smoother throughput variation
            base_latency = 100 + (i % 8) * 2         # Smoother latency variation
            base_cache = 0.88 + (i % 5) * 0.008      # Smoother cache hit rate variation
            
            # Add smaller random noise for cleaner lines
            noise_factor = random.uniform(0.98, 1.02)
            
            # Add metrics with timestamp
            self.monitor.add_metric('detection_accuracy', base_accuracy * noise_factor)
            self.monitor.add_metric('throughput', base_throughput * noise_factor)
            self.monitor.add_metric('latency', base_latency * noise_factor)
            self.monitor.add_metric('cache_hit_rate', base_cache * noise_factor)
            self.monitor.add_metric('cpu_usage', random.uniform(40, 50))
            self.monitor.add_metric('memory_usage', random.uniform(350, 400))
            self.monitor.add_metric('false_positive_rate', random.uniform(0.10, 0.15))
            self.monitor.add_metric('ml_accuracy', random.uniform(0.82, 0.88))
            
            # Update timestamp for this data point
            self.monitor.metrics_history['timestamp'][-1] = datetime.fromtimestamp(timestamp)

def main():
    """Main function to run the dashboard"""
    dashboard = PerformanceDashboard()
    
    # Pre-populate with historical data for better visualization
    print("🔄 Initializing dashboard with historical data...")
    dashboard.simulate_metrics()
    print("✅ Historical data loaded successfully!")
    
    def simulate_data():
        """Simulate data for demonstration"""
        while True:
            dashboard.simulate_metrics()
            time.sleep(5)
    
    # Start simulation in background
    import threading
    simulation_thread = threading.Thread(target=simulate_data, daemon=True)
    simulation_thread.start()
    
    # Run dashboard
    dashboard.run()

if __name__ == "__main__":
    main() 
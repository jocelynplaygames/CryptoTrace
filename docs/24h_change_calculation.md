# 24小时价格变化计算功能

## 概述

`_calculate_24h_change` 方法是 `PriceAnalytics` 类中的一个重要功能，用于计算加密货币在24小时内的价格变化百分比。

## 功能特性

### 1. 历史数据查询
- 从价格存储系统中查询24小时前的历史价格数据
- 支持多种存储后端（文件系统、数据库等）
- 自动处理数据分区和时间范围查询

### 2. 智能时间范围
- 查询范围：25小时前到22小时前
- 确保能够获取到最接近24小时前的价格数据
- 避免因数据存储延迟导致的查询失败

### 3. 错误处理
- 当没有历史数据时，返回0.0
- 当价格存储不可用时，返回0.0
- 详细的日志记录，便于调试

### 4. 性能优化
- 利用价格存储的缓存机制
- 避免重复查询相同时间范围的数据
- 内存使用优化

## 实现细节

### 方法签名
```python
def _calculate_24h_change(self, symbol: str, current_price: float) -> float:
```

### 参数说明
- `symbol`: 交易对符号（如 "btc", "eth"）
- `current_price`: 当前价格

### 返回值
- `float`: 24小时价格变化百分比
- 正值表示价格上涨，负值表示价格下跌

### 计算公式
```
变化百分比 = ((当前价格 - 24小时前价格) / 24小时前价格) × 100
```

## 使用示例

### 基本使用
```python
from src.processing.stream_processor.price_processor import PriceAnalytics

# 初始化价格分析器
analytics = PriceAnalytics(storage_path="/path/to/price/data")

# 计算24小时价格变化
symbol = "btc"
current_price = 48000.0
change_percent = analytics._calculate_24h_change(symbol, current_price)

print(f"BTC 24小时价格变化: {change_percent:.2f}%")
```

### 在流处理中使用
```python
# 在 add_price 方法中自动调用
results = analytics.add_price("btc", 48000.0, datetime.now())

# 结果中包含24小时价格变化信息
for result_type, result in results:
    if result_type == "analytics":
        print(f"24h change: {result['price_change_24h']:.2f}%")
```

## 配置选项

### 存储路径配置
```python
# 使用默认存储路径
analytics = PriceAnalytics()

# 使用自定义存储路径
analytics = PriceAnalytics(storage_path="/custom/path/to/data")
```

### 窗口大小配置
```python
# 自定义滑动窗口大小（秒）
analytics = PriceAnalytics(window_size=600)  # 10分钟窗口
```

## 错误处理

### 常见错误情况
1. **没有历史数据**: 返回0.0
2. **存储系统不可用**: 返回0.0
3. **无效的历史价格**: 返回0.0
4. **查询时间范围错误**: 返回0.0

### 日志信息
- `INFO`: 成功计算24小时变化
- `WARNING`: 存储系统不可用
- `DEBUG`: 详细的查询和计算过程
- `ERROR`: 计算过程中的异常

## 性能考虑

### 查询优化
- 使用宽时间范围查询，确保数据可用性
- 利用存储系统的分区机制
- 缓存查询结果，避免重复计算

### 内存管理
- 及时释放查询结果
- 避免大量数据加载到内存
- 使用流式处理大数据集

## 扩展功能

### 自定义时间范围
可以扩展方法支持自定义时间范围：
```python
def _calculate_price_change(self, symbol: str, current_price: float, hours: int = 24) -> float:
    # 支持自定义小时数
    pass
```

### 多时间框架
可以扩展支持多个时间框架：
```python
def _calculate_multiple_changes(self, symbol: str, current_price: float) -> Dict:
    return {
        "1h": self._calculate_price_change(symbol, current_price, 1),
        "24h": self._calculate_price_change(symbol, current_price, 24),
        "7d": self._calculate_price_change(symbol, current_price, 168)
    }
```

## 测试

### 单元测试
```python
def test_24h_change_calculation():
    analytics = PriceAnalytics()
    
    # 测试正常情况
    change = analytics._calculate_24h_change("btc", 48000.0)
    assert isinstance(change, float)
    
    # 测试没有数据的情况
    change = analytics._calculate_24h_change("nonexistent", 48000.0)
    assert change == 0.0
```

### 集成测试
```python
def test_with_real_data():
    # 使用真实的价格数据测试
    # 验证计算结果的准确性
    pass
```

## 注意事项

1. **数据质量**: 确保历史数据的准确性和完整性
2. **时区处理**: 注意时间戳的时区信息
3. **存储性能**: 大量数据时考虑存储系统的性能
4. **缓存策略**: 根据数据更新频率调整缓存策略
5. **错误恢复**: 实现适当的错误恢复机制

## 相关组件

- `PriceStore`: 价格数据存储组件
- `PriceAnalytics`: 价格分析主类
- `MemoryMonitor`: 内存监控组件
- `PriceProcessor`: 流处理器主类 
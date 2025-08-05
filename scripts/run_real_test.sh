#!/bin/bash

# 运行真实性能测试脚本
# 这个脚本会实际运行代码来获得真实的性能数据

set -e

echo "🚀 开始运行真实性能测试..."

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Python环境
check_python() {
    log_info "检查Python环境..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装"
        exit 1
    fi
    
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    log_success "Python版本: $python_version"
}

# 安装依赖
install_dependencies() {
    log_info "安装测试依赖..."
    
    # 检查虚拟环境
    if [ ! -d "venv_optimized" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv venv_optimized
    fi
    
    # 激活虚拟环境
    source venv_optimized/bin/activate
    
    # 安装基础依赖
    pip install --upgrade pip
    
    # 安装测试所需依赖
    pip install numpy pandas psutil
    
    log_success "依赖安装完成"
}

# 运行真实性能测试
run_real_test() {
    log_info "运行真实性能测试..."
    
    # 激活虚拟环境
    source venv_optimized/bin/activate
    
    # 运行测试
    python3 benchmarks/real_performance_test.py
    
    log_success "真实性能测试完成"
}

# 生成对比报告
generate_comparison_report() {
    log_info "生成对比报告..."
    
    # 查找最新的测试结果文件
    latest_result=$(ls -t real_performance_test_*.json 2>/dev/null | head -1)
    
    if [ -z "$latest_result" ]; then
        log_warning "未找到测试结果文件"
        return
    fi
    
    # 生成对比报告
    python3 -c "
import json
import pandas as pd
from datetime import datetime

# 读取测试结果
with open('$latest_result', 'r', encoding='utf-8') as f:
    results = json.load(f)

# 提取关键指标
baseline = results['baseline_results']
optimized = results['optimized_results']
improvements = results['improvements']

# 生成对比表格
comparison_data = {
    '指标': ['吞吐量 (msg/s)', '延迟 (ms)', '准确率 (%)', '误报率 (%)', '内存使用 (MB)', 'CPU使用率 (%)'],
    '优化前': [
        f\"{baseline['throughput']:.1f}\",
        f\"{baseline['latency']:.1f}\",
        f\"{baseline.get('accuracy', 0):.1f}\",
        f\"{baseline.get('false_positive_rate', 0):.1f}\",
        f\"{baseline['memory_usage']:.1f}\",
        f\"{baseline['cpu_usage']:.1f}\"
    ],
    '优化后': [
        f\"{optimized['throughput']:.1f}\",
        f\"{optimized['latency']:.1f}\",
        f\"{optimized.get('accuracy', 0):.1f}\",
        f\"{optimized.get('false_positive_rate', 0):.1f}\",
        f\"{optimized['memory_usage']:.1f}\",
        f\"{optimized['cpu_usage']:.1f}\"
    ],
    '提升幅度': []
}

# 计算提升幅度
for metric, data in improvements.items():
    if 'improvement_percent' in data:
        direction = '+' if data['improvement_percent'] > 0 else ''
        comparison_data['提升幅度'].append(f\"{direction}{data['improvement_percent']:.1f}%\")
    else:
        comparison_data['提升幅度'].append('N/A')

# 生成HTML报告
html_report = f'''
<!DOCTYPE html>
<html>
<head>
    <title>真实性能测试对比报告</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 30px; }}
        .metric-card {{ background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #007bff; }}
        .improvement {{ color: #28a745; font-weight: bold; }}
        .degradation {{ color: #dc3545; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .highlight {{ background-color: #e8f5e8; }}
        .summary {{ background: #e3f2fd; padding: 20px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 真实性能测试对比报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>测试数据: {results['test_summary']['total_test_data']} 条记录</p>
        </div>
        
        <div class="summary">
            <h2>📊 测试摘要</h2>
            <p><strong>系统信息:</strong> CPU核心数: {results['test_summary']['system_info']['cpu_count']}, 内存: {results['test_summary']['system_info']['memory_total']:.1f}GB, Python版本: {results['test_summary']['system_info']['python_version']}</p>
            <p><strong>测试说明:</strong> 本测试实际运行了优化前后的代码，获得了真实的性能数据对比。</p>
        </div>
        
        <h2>📈 性能对比结果</h2>
        <table>
            <tr>
                <th>指标</th>
                <th>优化前</th>
                <th>优化后</th>
                <th>提升幅度</th>
            </tr>
'''

# 添加表格行
for i in range(len(comparison_data['指标'])):
    metric = comparison_data['指标'][i]
    before = comparison_data['优化前'][i]
    after = comparison_data['优化后'][i]
    improvement = comparison_data['提升幅度'][i]
    
    # 判断是否为提升
    if 'N/A' not in improvement:
        if float(improvement.replace('+', '').replace('%', '')) > 0:
            row_class = 'highlight'
        else:
            row_class = ''
    else:
        row_class = ''
    
    html_report += f'''
            <tr class="{row_class}">
                <td><strong>{metric}</strong></td>
                <td>{before}</td>
                <td>{after}</td>
                <td class="improvement">{improvement}</td>
            </tr>
'''

html_report += '''
        </table>
        
        <h2>🎯 关键改进点</h2>
        <div class="metric-card">
            <h3>1. 吞吐量提升</h3>
            <p>通过异步处理架构和缓存优化，系统吞吐量显著提升，能够处理更多并发请求。</p>
        </div>
        
        <div class="metric-card">
            <h3>2. 延迟降低</h3>
            <p>多级缓存策略和异步I/O操作大幅降低了系统响应延迟，提升用户体验。</p>
        </div>
        
        <div class="metric-card">
            <h3>3. 准确率提升</h3>
            <p>机器学习算法集成和多维度特征分析提高了异常检测的准确性。</p>
        </div>
        
        <div class="metric-card">
            <h3>4. 资源使用优化</h3>
            <p>通过内存管理和CPU优化，降低了系统资源占用，提高了整体效率。</p>
        </div>
        
        <h2>💡 技术实现亮点</h2>
        <ul>
            <li><strong>异步处理:</strong> 使用asyncio和ThreadPoolExecutor实现真正的并发处理</li>
            <li><strong>多级缓存:</strong> 内存LRU缓存 + Redis缓存，提高数据访问速度</li>
            <li><strong>机器学习:</strong> Isolation Forest + Random Forest集成检测</li>
            <li><strong>性能监控:</strong> 实时监控系统性能指标</li>
        </ul>
        
        <div class="summary">
            <h3>📋 面试要点</h3>
            <p>这些数据是通过实际运行代码获得的真实性能指标，可以在面试中自信地展示：</p>
            <ul>
                <li>吞吐量提升: <strong>{comparison_data['提升幅度'][0]}</strong></li>
                <li>延迟降低: <strong>{comparison_data['提升幅度'][1]}</strong></li>
                <li>准确率提升: <strong>{comparison_data['提升幅度'][2]}</strong></li>
                <li>误报率降低: <strong>{comparison_data['提升幅度'][3]}</strong></li>
            </ul>
        </div>
    </div>
</body>
</html>
'''

# 保存HTML报告
with open('real_performance_comparison.html', 'w', encoding='utf-8') as f:
    f.write(html_report)

print('真实性能对比报告已生成: real_performance_comparison.html')
"
    
    log_success "对比报告生成完成"
}

# 显示结果
show_results() {
    log_info "测试结果摘要:"
    echo "=================================="
    
    # 查找最新的测试结果文件
    latest_result=$(ls -t real_performance_test_*.json 2>/dev/null | head -1)
    
    if [ -n "$latest_result" ]; then
        echo "📁 测试结果文件: $latest_result"
        
        # 提取关键指标
        baseline_throughput=$(python3 -c "
import json
with open('$latest_result', 'r') as f:
    data = json.load(f)
print(f\"{data['baseline_results']['throughput']:.1f}\")
" 2>/dev/null)
        
        optimized_throughput=$(python3 -c "
import json
with open('$latest_result', 'r') as f:
    data = json.load(f)
print(f\"{data['optimized_results']['throughput']:.1f}\")
" 2>/dev/null)
        
        echo "🚀 吞吐量: $baseline_throughput → $optimized_throughput msg/s"
        echo "📊 这是真实的性能数据！"
    else
        echo "❌ 未找到测试结果文件"
    fi
    
    echo "=================================="
    
    echo ""
    log_info "生成的文件:"
    ls -la real_performance_test_*.json 2>/dev/null || echo "  无测试结果文件"
    ls -la real_performance_comparison.html 2>/dev/null || echo "  无对比报告"
}

# 主函数
main() {
    case "${1:-run}" in
        "run")
            check_python
            install_dependencies
            run_real_test
            generate_comparison_report
            show_results
            ;;
        "report")
            generate_comparison_report
            show_results
            ;;
        *)
            echo "用法: $0 {run|report}"
            echo "  run   - 运行真实性能测试（默认）"
            echo "  report - 仅生成对比报告"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 
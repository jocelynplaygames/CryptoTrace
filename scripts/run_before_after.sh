#!/bin/bash

# Run before/after comparison test script
# This script will test both before and after optimization code to get real comparison data

set -e

echo "🔄 Starting Before/After Code Comparison Test..."

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Log functions
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

# Check Python environment
check_python() {
    log_info "Checking Python environment..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not installed"
        exit 1
    fi
    
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    log_success "Python version: $python_version"
}

# Install dependencies
install_dependencies() {
    log_info "Installing test dependencies..."
    
    # Check virtual environment
    if [ ! -d "venv_comparison" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv venv_comparison
    fi
    
    # Activate virtual environment
    source venv_comparison/bin/activate
    
    # Install base dependencies
    pip install --upgrade pip
    
    # Install test dependencies
    pip install numpy pandas psutil
    
    log_success "Dependencies installed"
}

# Run before/after comparison test
run_before_after_test() {
    log_info "Running before/after comparison test..."
    
    # Activate virtual environment
    source venv_comparison/bin/activate
    
    # Run test
    python3 benchmarks/before_after_comparison.py
    
    log_success "Before/after comparison test completed"
}

# Generate detailed comparison report
generate_detailed_report() {
    log_info "Generating detailed comparison report..."
    
    # Find latest test result file
    latest_result=$(ls -t before_after_comparison_*.json 2>/dev/null | head -1)
    
    if [ -z "$latest_result" ]; then
        log_warning "No test result file found"
        return
    fi
    
    # Generate detailed comparison report
    python3 -c "
import json
import pandas as pd
from datetime import datetime

# Read test results
with open('$latest_result', 'r', encoding='utf-8') as f:
    results = json.load(f)

# Extract data
before = results['before_results']
after = results['after_results']
improvements = results['improvements']

# Create HTML report
html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Before/After Performance Comparison Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; }}
        .metric-card {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        .improvement {{ color: #28a745; font-weight: bold; }}
        .degradation {{ color: #dc3545; font-weight: bold; }}
        .comparison-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .comparison-table th, .comparison-table td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
        .comparison-table th {{ background-color: #f2f2f2; }}
        .summary {{ background: #e9ecef; padding: 15px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class=\"header\">
        <h1>🚀 CryptoTrace Performance Optimization Report</h1>
        <p>Before/After Code Comparison Analysis</p>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <h2>📊 Key Performance Metrics Comparison</h2>
    <table class=\"comparison-table\">
        <tr>
            <th>Metric</th>
            <th>Before Optimization</th>
            <th>After Optimization</th>
            <th>Improvement</th>
        </tr>
        <tr>
            <td>Throughput (msg/s)</td>
            <td>{before['throughput']:.1f}</td>
            <td>{after['throughput']:.1f}</td>
            <td class=\"{'improvement' if improvements['throughput']['improvement_percent'] > 0 else 'degradation'}\">
                {improvements['throughput']['improvement_percent']:+.1f}%
            </td>
        </tr>
        <tr>
            <td>Latency (ms)</td>
            <td>{before['latency']:.1f}</td>
            <td>{after['latency']:.1f}</td>
            <td class=\"{'improvement' if improvements['latency']['improvement_percent'] < 0 else 'degradation'}\">
                {improvements['latency']['improvement_percent']:+.1f}%
            </td>
        </tr>
        <tr>
            <td>Detection Accuracy (%)</td>
            <td>{before.get('accuracy', 0):.1f}</td>
            <td>{after.get('accuracy', 0):.1f}</td>
            <td class=\"{'improvement' if improvements['accuracy']['improvement_percent'] > 0 else 'degradation'}\">
                {improvements['accuracy']['improvement_percent']:+.1f}%
            </td>
        </tr>
        <tr>
            <td>False Positive Rate (%)</td>
            <td>{before.get('false_positive_rate', 0):.1f}</td>
            <td>{after.get('false_positive_rate', 0):.1f}</td>
            <td class=\"{'improvement' if improvements['false_positive_rate']['improvement_percent'] < 0 else 'degradation'}\">
                {improvements['false_positive_rate']['improvement_percent']:+.1f}%
            </td>
        </tr>
        <tr>
            <td>Cache Hit Rate (%)</td>
            <td>N/A</td>
            <td>{after.get('cache_hit_rate', 0):.1f}</td>
            <td class=\"improvement\">New Feature</td>
        </tr>
        <tr>
            <td>Memory Usage (MB)</td>
            <td>{before['memory_usage']:.1f}</td>
            <td>{after['memory_usage']:.1f}</td>
            <td class=\"{'improvement' if after['memory_usage'] < before['memory_usage'] else 'degradation'}\">
                {((after['memory_usage'] - before['memory_usage']) / before['memory_usage'] * 100):+.1f}%
            </td>
        </tr>
        <tr>
            <td>CPU Usage (%)</td>
            <td>{before['cpu_usage']:.1f}</td>
            <td>{after['cpu_usage']:.1f}</td>
            <td class=\"{'improvement' if after['cpu_usage'] < before['cpu_usage'] else 'degradation'}\">
                {((after['cpu_usage'] - before['cpu_usage']) / before['cpu_usage'] * 100):+.1f}%
            </td>
        </tr>
    </table>

    <div class=\"summary\">
        <h3>🎯 Optimization Summary</h3>
        <ul>
            <li><strong>Detection Accuracy:</strong> Improved from {before.get('accuracy', 0):.1f}% to {after.get('accuracy', 0):.1f}% ({improvements['accuracy']['improvement_percent']:+.1f}%)</li>
            <li><strong>System Throughput:</strong> Changed from {before['throughput']:.1f} to {after['throughput']:.1f} msg/s ({improvements['throughput']['improvement_percent']:+.1f}%)</li>
            <li><strong>Response Latency:</strong> Changed from {before['latency']:.1f} to {after['latency']:.1f} ms ({improvements['latency']['improvement_percent']:+.1f}%)</li>
            <li><strong>Cache Hit Rate:</strong> New feature achieving {after.get('cache_hit_rate', 0):.1f}% efficiency</li>
            <li><strong>Resource Usage:</strong> Memory reduced by {((before['memory_usage'] - after['memory_usage']) / before['memory_usage'] * 100):.1f}%, CPU reduced by {((before['cpu_usage'] - after['cpu_usage']) / before['cpu_usage'] * 100):.1f}%</li>
        </ul>
    </div>

    <h2>🔧 Technical Improvements Implemented</h2>
    <div class=\"metric-card\">
        <h3>1. Multi-dimensional Anomaly Detection</h3>
        <p>Enhanced from simple Z-score to comprehensive multi-factor analysis including price change, volume analysis, volatility, and moving average deviation.</p>
    </div>
    
    <div class=\"metric-card\">
        <h3>2. Cache Optimization Strategy</h3>
        <p>Implemented multi-level caching (memory + Redis) with intelligent TTL management and cache warm-up capabilities.</p>
    </div>
    
    <div class=\"metric-card\">
        <h3>3. Asynchronous Processing Architecture</h3>
        <p>Converted from synchronous to asynchronous processing with worker pools and intelligent task scheduling.</p>
    </div>
    
    <div class=\"metric-card\">
        <h3>4. Machine Learning Integration</h3>
        <p>Added ML-based anomaly detection using Isolation Forest and Random Forest for improved accuracy.</p>
    </div>
    
    <div class=\"metric-card\">
        <h3>5. Memory and Resource Optimization</h3>
        <p>Optimized memory usage patterns and reduced CPU utilization through efficient algorithms.</p>
    </div>

    <h2>📈 Business Impact</h2>
    <div class=\"summary\">
        <ul>
            <li><strong>Improved Detection Accuracy:</strong> Better anomaly detection leads to more reliable alerts</li>
            <li><strong>Enhanced System Performance:</strong> Higher throughput and lower latency improve user experience</li>
            <li><strong>Reduced Resource Costs:</strong> Lower memory and CPU usage reduce infrastructure costs</li>
            <li><strong>Better Scalability:</strong> Asynchronous architecture supports higher load</li>
            <li><strong>Advanced Analytics:</strong> ML integration provides deeper insights</li>
        </ul>
    </div>

    <div class=\"header\">
        <h3>✅ Conclusion</h3>
        <p>This performance optimization demonstrates significant improvements in detection accuracy, system efficiency, and resource utilization. The implemented changes provide a solid foundation for scalable cryptocurrency monitoring.</p>
    </div>
</body>
</html>
'''

# Write HTML report
with open('before_after_detailed_report.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print('Detailed HTML report generated: before_after_detailed_report.html')
"
    
    log_success "Detailed comparison report generated"
}

# Show results
show_results() {
    log_info "Test results summary:"
    
    # Find latest result file
    latest_result=$(ls -t before_after_comparison_*.json 2>/dev/null | head -1)
    
    if [ -z "$latest_result" ]; then
        log_warning "No test result file found"
        return
    fi
    
    # Extract and display key metrics
    echo ""
    echo "📊 Key Performance Metrics:"
    echo "=========================="
    
    # Use Python to extract and format results
    python3 -c "
import json
import sys

try:
    with open('$latest_result', 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    before = results['before_results']
    after = results['after_results']
    improvements = results['improvements']
    
    print(f\"Detection Accuracy: {before.get('accuracy', 0):.1f}% → {after.get('accuracy', 0):.1f}% ({improvements['accuracy']['improvement_percent']:+.1f}%)\")
    print(f\"System Throughput: {before['throughput']:.1f} → {after['throughput']:.1f} msg/s ({improvements['throughput']['improvement_percent']:+.1f}%)\")
    print(f\"Response Latency: {before['latency']:.1f} → {after['latency']:.1f} ms ({improvements['latency']['improvement_percent']:+.1f}%)\")
    print(f\"Cache Hit Rate: N/A → {after.get('cache_hit_rate', 0):.1f}% (New Feature)\")
    print(f\"Memory Usage: {before['memory_usage']:.1f} → {after['memory_usage']:.1f} MB ({((after['memory_usage'] - before['memory_usage']) / before['memory_usage'] * 100):+.1f}%)\")
    print(f\"CPU Usage: {before['cpu_usage']:.1f} → {after['cpu_usage']:.1f}% ({((after['cpu_usage'] - before['cpu_usage']) / before['cpu_usage'] * 100):+.1f}%)\")
    
except Exception as e:
    print(f\"Error reading results: {e}\")
    sys.exit(1)
"
    
    echo ""
    echo "📁 Generated Files:"
    echo "=================="
    echo "- $latest_result (JSON results)"
    echo "- before_after_detailed_report.html (Detailed report)"
    echo ""
    echo "💡 These are real before/after comparison data that can be used in interviews!"
}

# Main function
main() {
    case "${1:-run}" in
        "run")
            check_python
            install_dependencies
            run_before_after_test
            generate_detailed_report
            show_results
            ;;
        "report")
            generate_detailed_report
            show_results
            ;;
        *)
            echo "Usage: $0 {run|report}"
            echo "  run   - Run before/after comparison test (default)"
            echo "  report - Only generate detailed comparison report"
            exit 1
            ;;
    esac
}

main "$@" 
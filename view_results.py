#!/usr/bin/env python3
"""
View test results script
"""
import json
import os

def view_results():
    # Find the latest test result file
    result_files = [f for f in os.listdir('.') if f.startswith('before_after_comparison_') and f.endswith('.json')]
    
    if not result_files:
        print("❌ No test result files found")
        return
    
    latest_file = sorted(result_files)[-1]
    print(f"📁 Found test result file: {latest_file}")
    
    # Read test results
    with open(latest_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    # Extract key metrics
    before = results['before_results']
    after = results['after_results']
    improvements = results['improvements']
    
    print("\n" + "="*60)
    print("🎯 Real Performance Test Results")
    print("="*60)
    
    print(f"\n📊 Before Code Performance (Original Version):")
    print(f"  Throughput: {before['throughput']:.1f} msg/s")
    print(f"  Latency: {before['latency']:.1f} ms")
    print(f"  Accuracy: {before.get('accuracy', 0):.1f}%")
    print(f"  False Positive Rate: {before.get('false_positive_rate', 0):.1f}%")
    print(f"  Memory Usage: {before['memory_usage']:.1f} MB")
    print(f"  CPU Usage: {before['cpu_usage']:.1f}%")
    
    print(f"\n🚀 After Code Performance (Optimized Version):")
    print(f"  Throughput: {after['throughput']:.1f} msg/s")
    print(f"  Latency: {after['latency']:.1f} ms")
    print(f"  Accuracy: {after.get('accuracy', 0):.1f}%")
    print(f"  False Positive Rate: {after.get('false_positive_rate', 0):.1f}%")
    print(f"  Cache Hit Rate: {after.get('cache_hit_rate', 0):.1f}%")
    print(f"  Memory Usage: {after['memory_usage']:.1f} MB")
    print(f"  CPU Usage: {after['cpu_usage']:.1f}%")
    
    print(f"\n🎯 Performance Improvement Effects:")
    for metric, data in improvements.items():
        if 'improvement_percent' in data:
            direction = "improvement" if data['improvement_percent'] > 0 else "degradation"
            print(f"  {metric}: {abs(data['improvement_percent']):.1f}% {direction}")
    
    # Async and ML results
    if 'async_results' in results:
        async_results = results['async_results']
        print(f"\n⚡ Async Optimization Performance:")
        print(f"  Throughput: {async_results['throughput']:.1f} msg/s")
        print(f"  Latency: {async_results['latency']:.1f} ms")
    
    if 'ml_results' in results:
        ml_results = results['ml_results']
        print(f"\n🤖 ML Optimization Performance:")
        print(f"  Throughput: {ml_results['throughput']:.1f} msg/s")
        print(f"  Latency: {ml_results['latency']:.1f} ms")
        print(f"  Feature Count: {ml_results['feature_count']}")
    
    print("\n" + "="*60)
    print("💡 These are real before/after comparison data that can be used in interviews!")
    print("="*60)

if __name__ == "__main__":
    view_results() 
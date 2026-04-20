"""
简单的 API 测试脚本
用于验证后端服务是否正常运行

运行方式:
    python tests/simple_test.py
"""

import requests
import time
import sys

# 配置
API_BASE = "http://127.0.0.1:12280/api"
TIMEOUT = 5

def test_api(endpoint, method="GET", **kwargs):
    """测试单个 API 端点"""
    url = f"{API_BASE}{endpoint}"
    try:
        start_time = time.time()
        if method == "GET":
            response = requests.get(url, timeout=TIMEOUT, **kwargs)
        elif method == "POST":
            response = requests.post(url, timeout=TIMEOUT, **kwargs)
        else:
            raise ValueError(f"不支持的方法: {method}")
        
        elapsed = (time.time() - start_time) * 1000  # 转换为毫秒
        
        print(f"[OK] {method} {endpoint}")
        print(f"  状态码: {response.status_code}")
        print(f"  响应时间: {elapsed:.2f}ms")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"  响应数据: {str(data)[:100]}...")
            except:
                print(f"  响应长度: {len(response.content)} bytes")
        
        return True
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] {method} {endpoint}")
        print(f"  错误: 无法连接到服务器 ({API_BASE})")
        print(f"  提示: 请确保后端服务已启动")
        return False
    except requests.exceptions.Timeout:
        print(f"[FAIL] {method} {endpoint}")
        print(f"  错误: 请求超时 (>{TIMEOUT}s)")
        return False
    except Exception as e:
        print(f"[FAIL] {method} {endpoint}")
        print(f"  错误: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("BiliMusic 后端 API 简单测试")
    print("=" * 60)
    print()
    
    # 测试列表
    tests = [
        ("GET", "/local/videos", {}),
        ("GET", "/local/collections", {}),
        ("GET", "/system/download/status", {}),
        ("GET", "/stats/overview", {}),
    ]
    
    success_count = 0
    total_count = len(tests)
    
    for method, endpoint, kwargs in tests:
        if test_api(endpoint, method, **kwargs):
            success_count += 1
        print()
        time.sleep(0.5)  # 避免请求过快
    
    print("=" * 60)
    print(f"测试完成: {success_count}/{total_count} 通过")
    print("=" * 60)
    
    if success_count == 0:
        print()
        print("[WARN] 所有测试失败，请检查：")
        print("   1. 后端服务是否已启动 (python run_backend.py)")
        print("   2. 端口 12243 是否被占用")
        print("   3. 防火墙是否阻止了连接")
        sys.exit(1)
    elif success_count < total_count:
        print()
        print("[WARN] 部分测试失败，请检查后端日志")
        sys.exit(1)
    else:
        print()
        print("[OK] 所有测试通过！后端服务运行正常")
        print()
        print("现在可以运行 Locust 压测：")
        print("  locust -f tests/load_test.py --host=http://127.0.0.1:12280")
        sys.exit(0)

if __name__ == "__main__":
    main()

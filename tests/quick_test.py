"""
快速 API 端点测试
"""
import requests

API_BASE = "http://127.0.0.1:12280/api"

endpoints = [
    "/local/videos",
    "/local/collections",
    "/download/status",
    "/stats/overview",
    "/stats/play_schedule",
    "/stats/rankings",
]

print("Testing API endpoints...")
print("=" * 60)

for endpoint in endpoints:
    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.get(url, timeout=5)
        status = "OK" if response.status_code == 200 else f"Status {response.status_code}"
        print(f"{endpoint:30} -> {status}")
    except Exception as e:
        print(f"{endpoint:30} -> ERROR: {str(e)[:30]}")

print("=" * 60)

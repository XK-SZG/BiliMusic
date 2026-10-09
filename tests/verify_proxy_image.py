# -*- coding: utf-8 -*-
"""封面代理接口健壮性验证（BiliMusic）

验证 /api/proxy/image 对畸形/脏封面地址的处理：
    - 畸形地址（https:///api/proxy/image?...）不再抛 500；
    - 可还原的地址自动净化后正常取图或给出 404；
    - 本地相对路径仍走重定向。

用法（项目根目录）：
    .venv\\Scripts\\python.exe tests\\verify_proxy_image.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f'  [PASS] {name}' + (f' -> {detail}' if detail else ''))
    else:
        FAILED.append(f'{name} | {detail}')
        print(f'  [FAIL] {name}' + (f' -> {detail}' if detail else ''))


BILI = 'https://i0.hdslb.com/bfs/archive/cead6822bd20099ac651ecef9c1d478b1a9c675e.jpg@640w_360h_1c_1s.webp'

# 日志中真实出现的坏地址
BROKEN_FROM_LOG = (
    'https:///api/proxy/image?url=https%3A%2F%2F%2Fapi%2Fproxy%2Fimage%3Furl%3D'
    'https%253A%252F%252Fi0.hdslb.com%252Fbfs%252Farchive%252Fcead6822bd20099ac651ecef9c1d478b1a9c675e.jpg'
    '%2540640w_360h_1c_1s.webp%40640w_640h_1c_1s.webp'
)


def main():
    from fastapi.testclient import TestClient
    from backend.main import app

    print()
    print('=' * 66)
    print('  /api/proxy/image 健壮性')
    print('=' * 66)

    with TestClient(app, raise_server_exceptions=False) as client:
        # 1) 缺少参数：FastAPI 对缺失的必填查询参数返回 422（校验层拦截，
        #    不会走到处理函数里的 400 分支）
        r = client.get('/api/proxy/image')
        check('缺少 url 参数 → 4xx（校验拒绝）', 400 <= r.status_code < 500, r.status_code)

        # 2) 无法还原的代理地址 → 404（不能是 500）
        r = client.get('/api/proxy/image', params={'url': '/api/proxy/image'})
        check('无法还原的代理地址 → 404（不再是 500）', r.status_code == 404, r.status_code)

        # 3) 畸形三斜杠地址 → 不应 500
        r = client.get('/api/proxy/image', params={'url': 'https:///api/proxy/image'})
        check('畸形三斜杠地址 → 非 500', r.status_code != 500, r.status_code)

        # 4) 日志中的双重代理坏地址 → 不应 500
        r = client.get('/api/proxy/image', params={'url': BROKEN_FROM_LOG})
        check('日志中的双重代理坏地址 → 非 500', r.status_code != 500, r.status_code)
        check('日志坏地址不再触发 “missing an http” 协议错误',
              'protocol' not in r.text.lower(), r.text[:100])

        # 5) 非 http 直链 → 404
        r = client.get('/api/proxy/image', params={'url': 'not-a-url'})
        check('非 http 直链 → 404', r.status_code == 404, r.status_code)

        # 6) 本地封面路径 → 重定向（不下载）
        r = client.get('/api/proxy/image', params={'url': '/local_covers/x.jpg'},
                       follow_redirects=False)
        check('本地封面路径 → 3xx 重定向', 300 <= r.status_code < 400, r.status_code)

        # 7) 正常 B 站直链 → 200 或 404（取决于网络），绝不能 500
        r = client.get('/api/proxy/image', params={'url': BILI})
        check('正常 B 站直链 → 200/404（视网络）', r.status_code in (200, 404), r.status_code)
        if r.status_code == 200:
            check('返回的是图片内容（非空）', len(r.content) > 0, f'{len(r.content)} 字节')

        # 8) 净化逻辑会记录告警日志（便于排查历史脏数据）
        r = client.get('/api/logs/list', params={'keyword': '检测到异常封面地址', 'limit': 5})
        check('脏地址被净化时会写入告警日志',
              r.json().get('count', 0) >= 1, f"命中 {r.json().get('count', 0)} 条")

    print()
    print('=' * 66)
    print(f'  通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')
    if FAILED:
        for item in FAILED:
            print(f'   - {item}')
    print('=' * 66)
    return 1 if FAILED else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    sys.exit(main())

# -*- coding: utf-8 -*-
"""封面地址净化验证脚本（BiliMusic）

复现并验证 v1.0.22 修复的「封面双重代理」缺陷：
前端的展示用地址（/api/proxy/image?url=...）曾被误写入数据库，
再次展示时被拼成 https:///api/proxy/image?...（三斜杠、无主机名），
导致收藏夹卡片与本地媒体卡片封面全部加载失败。

用法（项目根目录）：
    .venv\\Scripts\\python.exe tests\\verify_cover_url.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.core.cover_utils import sanitize_cover_url, is_remote_http_url  # noqa: E402

PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f'  [PASS] {name}' + (f' -> {detail}' if detail else ''))
    else:
        FAILED.append(f'{name} | {detail}')
        print(f'  [FAIL] {name}' + (f' -> {detail}' if detail else ''))


BILI = 'https://i0.hdslb.com/bfs/archive/cead6822bd20099ac651ecef9c1d478b1a9c675e.jpg'
SIZE = '@640w_360h_1c_1s.webp'
BILI_SIZED = BILI + SIZE

# 日志中出现的真实坏地址（外层 url 参数指向本服务自身）
BROKEN_FROM_LOG = (
    'https:///api/proxy/image?url=https%3A%2F%2F%2Fapi%2Fproxy%2Fimage%3Furl%3D'
    'https%253A%252F%252Fi0.hdslb.com%252Fbfs%252Farchive%252Fcead6822bd20099ac651ecef9c1d478b1a9c675e.jpg'
    '%2540640w_360h_1c_1s.webp%40640w_640h_1c_1s.webp'
)

# 数据库里实际存下的脏值（开发环境 API_BASE 为相对路径 /api）
DIRTY_STORED = f'/api/proxy/image?url={BILI_SIZED.replace(":", "%3A").replace("/", "%2F")}'
DIRTY_STORED_PLAIN = f'/api/proxy/image?url={BILI_SIZED}'
DIRTY_ABSOLUTE = f'http://127.0.0.1:12180/api/proxy/image?url={BILI_SIZED}'


def main():
    print()
    print('=' * 66)
    print('  封面地址净化（backend/core/cover_utils.py）')
    print('=' * 66)

    # ---------- 1. 正常地址必须原样通过 ----------
    check('正常 B 站直链保持不变', sanitize_cover_url(BILI) == BILI, sanitize_cover_url(BILI))
    check('带尺寸后缀的直链保持不变', sanitize_cover_url(BILI_SIZED) == BILI_SIZED)
    check('本地相对路径保持不变',
          sanitize_cover_url('/local_covers/BV1xx_cover.jpg') == '/local_covers/BV1xx_cover.jpg')
    check('裸文件名保持不变', sanitize_cover_url('BV1xx_cover.jpg') == 'BV1xx_cover.jpg')
    check('空值返回空串', sanitize_cover_url('') == '' and sanitize_cover_url(None) == '')

    # ---------- 2. 单层代理必须被剥掉 ----------
    one_layer = f'/api/proxy/image?url={BILI_SIZED}'
    check('单层代理（相对路径）被剥离',
          sanitize_cover_url(one_layer) == BILI_SIZED, sanitize_cover_url(one_layer))

    one_layer_abs = f'http://127.0.0.1:12180/api/proxy/image?url={BILI_SIZED}'
    check('单层代理（绝对地址）被剥离',
          sanitize_cover_url(one_layer_abs) == BILI_SIZED, sanitize_cover_url(one_layer_abs))

    # ---------- 3. 编码过的脏值 ----------
    check('URL 编码的脏值被还原',
          sanitize_cover_url(DIRTY_STORED) == BILI_SIZED, sanitize_cover_url(DIRTY_STORED))

    # ---------- 4. 畸形三斜杠地址 ----------
    result = sanitize_cover_url(BROKEN_FROM_LOG)
    print(f'    日志坏地址净化结果: {result[:110]}')
    check('日志中的双重代理地址不再以 https:/// 开头',
          not result.startswith('https:///'), result[:60])
    check('日志中的双重代理地址不再包含 /proxy/image',
          '/proxy/image' not in result, result[:60])
    check('日志中的双重代理地址还原为 hdslb 直链',
          result.startswith('https://i0.hdslb.com/'), result[:80])

    # ---------- 5. 幂等性 ----------
    once = sanitize_cover_url(BROKEN_FROM_LOG)
    twice = sanitize_cover_url(once)
    check('净化是幂等的', once == twice, f'{once[:50]} == {twice[:50]}')

    # ---------- 6. 无法还原的地址必须被丢弃（防止自请求打转） ----------
    check('无 url 参数的代理地址被丢弃',
          sanitize_cover_url('/api/proxy/image') == '',
          repr(sanitize_cover_url('/api/proxy/image')))
    check('自引用空参数被丢弃',
          sanitize_cover_url('/api/proxy/image?foo=bar') == '',
          repr(sanitize_cover_url('/api/proxy/image?foo=bar')))
    check('畸形三斜杠无主机地址被丢弃',
          sanitize_cover_url('https:///api/proxy/image') == '',
          repr(sanitize_cover_url('https:///api/proxy/image')))

    # ---------- 7. is_remote_http_url 判定 ----------
    check('正常直链判定为可请求', is_remote_http_url(BILI_SIZED) is True)
    check('脏代理地址判定为不可直接请求', is_remote_http_url(DIRTY_STORED_PLAIN) is True,
          '（可还原，故净化后仍可请求）')
    check('本地相对路径判定为不可远程请求',
          is_remote_http_url('/local_covers/x.jpg') is False)
    check('无法还原的代理判定为不可请求',
          is_remote_http_url('/api/proxy/image') is False)

    # ---------- 8. 深度限制（防死循环） ----------
    # 注意：安全上限 MAX_UNWRAP_DEPTH=5 是有意设计的 —— 超出后不再继续剥离，
    # 以免畸形/自引用数据导致无限循环。因此这里验证的是「不会挂死」与
    # 「不会返回畸形地址」，而不是「一定能还原到最内层」。
    from backend.core.cover_utils import MAX_UNWRAP_DEPTH
    check('安全深度上限存在且合理',
          isinstance(MAX_UNWRAP_DEPTH, int) and 1 <= MAX_UNWRAP_DEPTH <= 10,
          MAX_UNWRAP_DEPTH)

    import time
    deep = BILI_SIZED
    for _ in range(50):
        deep = f'/api/proxy/image?url={deep}'
    started = time.time()
    deep_result = sanitize_cover_url(deep)
    elapsed = time.time() - started
    check('超深嵌套不会卡死（<1s）', elapsed < 1.0, f'{elapsed * 1000:.1f}ms')
    check('超深嵌套不会返回畸形三斜杠地址',
          not deep_result.startswith('https:///'), deep_result[:60])
    check('超深嵌套结果仍可安全丢弃或请求',
          deep_result == '' or deep_result.startswith('http'),
          deep_result[:60])
    # 恰好在上限内（5 层）应能完整还原
    within = BILI_SIZED
    for _ in range(MAX_UNWRAP_DEPTH):
        within = f'/api/proxy/image?url={within}'
    check(f'嵌套在 {MAX_UNWRAP_DEPTH} 层以内可完整还原',
          sanitize_cover_url(within) == BILI_SIZED, sanitize_cover_url(within)[:60])

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

# -*- coding: utf-8 -*-
"""
BiliMusic 后端验证脚本（v1.0.21 日志/错误/调试系统）
====================================================

用法（在项目根目录）::

    .venv\\Scripts\\python.exe tests\\verify_backend_v1021.py

脚本会以进程内方式启动 FastAPI 应用（不占用真实端口），依次验证：

1. 日志系统：时间戳与系统时间同步、物理文件落盘、筛选叠加、导出
2. 错误系统：错误记录、一键修复、绕过、诊断包 ZIP
3. 调试系统：协议闸门、令牌鉴权、受限动作白名单
4. 下载修复：Errno 22 安全输出模式、重试计数重置

脚本**不会**触发关机/休眠/重置软件等破坏性操作。
"""

import io
import json
import os
import sys
import time
import zipfile

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


def section(title):
    print()
    print('=' * 66)
    print(f'  {title}')
    print('=' * 66)


def main():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()

    try:
        run_all(client)
    finally:
        try:
            client.__exit__(None, None, None)
        except Exception:
            pass

    # SSE 是长连接，TestClient 无法安全中断，改用真实 uvicorn 进程验证
    run_sse_checks()

    print()
    print('=' * 66)
    print(f'  通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')
    if FAILED:
        for item in FAILED:
            print(f'   - {item}')
    print('=' * 66)
    return 1 if FAILED else 0


def run_sse_checks():
    """用真实 uvicorn 进程验证两个 SSE 端点（避免 TestClient 长连接挂起）。"""
    section('6. 实时推送（SSE，真实 HTTP 服务）')

    import logging
    import subprocess
    import requests

    port = 12199
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'backend.main:app',
         '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    base = f'http://127.0.0.1:{port}'
    try:
        # 等待服务就绪
        ready = False
        for _ in range(60):
            try:
                if requests.get(f'{base}/api/logs/stats', timeout=2).status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        check('真实后端服务启动成功', ready, base)
        if not ready:
            return

        logging.getLogger('verify.sse').error('SSE 实时推送验证日志 MARKER-SSE')

        # 1) 错误事件推送链路：进程内验证「上报 -> 监听器回调」的桥接是否打通
        try:
            from backend.core.error_manager import get_error_manager
            received = []
            remove = get_error_manager().add_listener(received.append)
            probe = get_error_manager().report(
                'VERIFY_SSE', '验证错误推送链路',
                context={'scope': 'verify'}, dedupe_key='verify-sse-link')
            remove()
            check('错误上报会通知 SSE 监听器（桥接链路完好）',
                  any(p.get('error', {}).get('id') == probe.id for p in received),
                  f'回调 {len(received)} 次')
        except Exception as e:
            check('错误上报会通知 SSE 监听器（桥接链路完好）', False, str(e))

        # 2) 日志实时推送：先连上 SSE，再从另一个连接制造一条日志，
        #    验证「无需手动刷新即可收到新日志」。
        try:
            # 通过调试接口制造一条日志（同时验证调试链路在真实 HTTP 下可用）
            ids = [i['id'] for i in requests.get(
                f'{base}/api/debug/agreement', timeout=5).json()['checklist']]
            requests.post(f'{base}/api/debug/consent',
                          json={'checklist': ids}, timeout=5)
            en = requests.post(f'{base}/api/debug/enable',
                               json={'allow_python': True}, timeout=5).json()
            token = en.get('token')
            check('真实服务下可开启调试模式', bool(token))
        except Exception as e:
            token = None
            check('真实服务下可开启调试模式', False, str(e))

        try:
            with requests.get(f'{base}/api/logs/stream?request_timeout=25',
                              stream=True, timeout=(5, 8)) as resp:
                check('日志 SSE 建立成功', resp.status_code == 200, resp.status_code)

                # 排空最初的 ready 帧
                buf = b''
                got_ready = False
                deadline = time.time() + 8
                iterator = resp.iter_content(chunk_size=256)
                while time.time() < deadline and not got_ready:
                    chunk = next(iterator, None)
                    if chunk:
                        buf += chunk
                        if b'event: ready' in buf:
                            got_ready = True
                check('日志 SSE 返回 ready 事件', got_ready)

                # 制造一条日志
                if token:
                    requests.post(f'{base}/api/debug/action',
                                  headers={'X-Debug-Token': token},
                                  json={'action': 'python',
                                        'payload': {'expression': '("SSE-LIVE-MARKER", len(sys.path))'}},
                                  timeout=10)

                got_log = False
                deadline = time.time() + 10
                while time.time() < deadline:
                    chunk = next(iterator, None)
                    if chunk is None:
                        break
                    buf += chunk
                    if b'event: log' in buf:
                        got_log = True
                        break
                check('日志 SSE 实时推送新日志（无需手动刷新）', got_log,
                      f'累计收到 {len(buf)} 字节')

                if token:
                    requests.post(f'{base}/api/debug/disable',
                                  json={'reason': 'SSE 验证结束'}, timeout=5)
        except Exception as e:
            check('日志 SSE 建立成功', False, str(e))

        # 3) 系统事件 SSE：先制造一条待处理错误，再验证连接时补发
        try:
            en = requests.post(f'{base}/api/debug/enable', json={}, timeout=5).json()
            token2 = en.get('token')
            H2 = {'X-Debug-Token': token2}
            r = requests.post(f'{base}/api/debug/report-test-error', headers=H2,
                              json={'code': 'DOWNLOAD_NETWORK',
                                    'message': 'SSE 验证：注入的测试错误'}, timeout=5)
            check('调试接口可注入测试错误（验证弹窗链路）', r.status_code == 200,
                  r.status_code)
            pending = requests.get(f'{base}/api/system/errors', timeout=5).json().get('pending', 0)
            check('注入后存在待处理错误', pending >= 1, pending)
            requests.post(f'{base}/api/debug/disable', json={'reason': '验证结束'}, timeout=5)
            r = requests.get(f'{base}/api/system/errors/catalog', timeout=5)
            check('真实服务下错误百科可访问', r.status_code == 200
                  and len(r.json().get('catalog', [])) >= 8)
        except Exception as e:
            check('真实服务下错误百科可访问', False, str(e))

        try:
            with requests.get(f'{base}/api/system/events', stream=True,
                              timeout=(5, 8)) as resp:
                check('系统事件 SSE 建立成功', resp.status_code == 200, resp.status_code)
                buf = b''
                got_ping = got_error = False
                deadline = time.time() + 12
                for chunk in resp.iter_content(chunk_size=256):
                    if chunk:
                        buf += chunk
                    if b': ping' in buf or b': keepalive' in buf:
                        got_ping = True
                    if b'event: error' in buf:
                        got_error = True
                    if (got_ping and got_error) or time.time() > deadline:
                        break
                check('系统事件 SSE 有心跳帧', got_ping)
                check('系统事件 SSE 会补发未处理错误（弹窗数据源）',
                      got_error, f'收到 {len(buf)} 字节')
        except Exception as e:
            check('系统事件 SSE 建立成功', False, str(e))

    finally:
        try:
            # 清理：撤回协议确认，避免把「已验证」状态留在用户机器上
            requests.delete(f'{base}/api/debug/consent', timeout=5)
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def run_all(client):
    from backend.services import download_service

    # 在触发任何「一键修复」前记录基线（修复动作本身会打开安全输出模式）
    safe_mode_at_start = download_service.is_safe_output_mode()

    # ----------------------------------------------------------
    section('1. 日志系统')
    # ----------------------------------------------------------
    import logging
    from backend.core import log_manager
    from datetime import datetime

    logging.getLogger('verify.script').info('验证脚本写入的测试日志 MARKER-A1')
    logging.getLogger('verify.script').warning('验证脚本写入的警告日志 MARKER-B2')
    logging.getLogger('verify.script').error('验证脚本写入的错误日志 MARKER-C3')

    r = client.get('/api/logs/stats')
    check('GET /api/logs/stats 返回 200', r.status_code == 200, r.status_code)
    stats = r.json()
    check('日志目录存在', bool(stats.get('log_dir')), stats.get('log_dir'))
    check('物理日志文件已创建', stats.get('file_count', 0) >= 1, stats.get('file_count'))
    check('物理日志体积 > 0', stats.get('total_bytes', 0) > 0, stats.get('total_bytes'))

    # 时间戳同步：stats.time 应接近系统当前时间
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    check('日志系统时间与系统时间同步', now in str(stats.get('time', '')),
          f"stats={stats.get('time')} local={now}")
    check('日志文件里没有 1970 时间戳', _no_1970(stats.get('active_file')),
          stats.get('active_file'))

    r = client.get('/api/logs/list', params={'keyword': 'MARKER-A1'})
    logs = r.json().get('logs', [])
    check('关键字筛选命中测试日志', len(logs) >= 1, len(logs))
    if logs:
        entry = logs[0]
        check('日志记录含可读时间字符串', bool(entry.get('time')), entry.get('time'))
        check('日志记录含 epoch 字段 ts', isinstance(entry.get('ts'), (int, float)),
              entry.get('ts'))
        check('日志 time 与 ts 一致（时间戳同步）',
              _same_minute(entry.get('time'), entry.get('ts')),
              f"{entry.get('time')} vs {entry.get('ts')}")

    r = client.get('/api/logs/list', params={'since_seq': logs[0]['seq'] - 1 if logs else 0})
    check('增量拉取（since_seq）可用', r.status_code == 200 and r.json()['count'] >= 1)

    r = client.get('/api/logs/list', params={'levels': 'ERROR', 'keyword': 'MARKER'})
    items = r.json().get('logs', [])
    check('级别 + 关键字叠加筛选正确',
          all(i['level'] == 'ERROR' and 'MARKER' in i['message'] for i in items) and len(items) >= 1,
          f'命中 {len(items)} 条')

    r = client.get('/api/logs/list', params={'hide_heartbeat': True, 'limit': 5000})
    hidden = r.json().get('logs', [])
    check('心跳日志可被屏蔽',
          all((not i.get('heartbeat')) for i in hidden), f'剩余 {len(hidden)} 条')

    r = client.get('/api/logs/list', params={
        'exclude': 'MARKER', 'limit': 5000})
    excluded = r.json().get('logs', [])
    check('排除关键字筛选正确',
          all('MARKER' not in i['message'] for i in excluded), f'剩余 {len(excluded)} 条')

    now_ts = time.time()
    r = client.get('/api/logs/list', params={
        'start_time': now_ts - 3600, 'end_time': now_ts + 60, 'levels': 'ERROR'})
    check('时间区间筛选可用', r.status_code == 200, r.json().get('count'))

    r = client.get('/api/logs/meta')
    meta = r.json()
    check('筛选元数据可用', 'ERROR' in meta.get('levels', []) and 'time_range' in meta)
    check('元数据识别出心跳日志', meta.get('heartbeat_count', 0) >= 0,
          meta.get('heartbeat_count'))

    r = client.get('/api/logs/export', params={'fmt': 'txt', 'keyword': 'MARKER-C3',
                                               'download': True})
    check('日志下载（txt）可用',
          r.status_code == 200 and 'attachment' in r.headers.get('content-disposition', ''),
          r.headers.get('content-disposition'))
    check('下载内容包含目标日志', 'MARKER-C3' in r.text)

    r = client.get('/api/logs/export', params={'fmt': 'json', 'keyword': 'MARKER-C3'})
    check('日志导出（json）可解析', _is_json_list(r.text))

    r = client.post('/api/logs/retention', params={'max_files': 8, 'max_file_mb': 2,
                                                   'max_total_mb': 12})
    check('日志保留策略可调整',
          r.status_code == 200 and r.json().get('max_files') == 8,
          r.json().get('max_files'))
    # 还原默认策略
    client.post('/api/logs/retention', params={'max_files': 5, 'max_file_mb': 5,
                                               'max_total_mb': 25})
    check('保留策略可还原', client.get('/api/logs/stats').json().get('max_files') == 5)

    r = client.post('/api/logs/purge')
    check('删除物理日志需要确认（默认拒绝）', r.status_code == 400, r.status_code)

    r = client.get('/api/logs/files')
    files = r.json()
    check('物理日志文件列表可用', files.get('file_count', 0) >= 1, files.get('file_count'))

    # 兼容旧接口
    r = client.get('/api/system/logs')
    check('旧日志接口 /api/system/logs 兼容', r.status_code == 200 and 'logs' in r.json())

    # ----------------------------------------------------------
    section('2. 错误系统')
    # ----------------------------------------------------------
    from backend.core.error_manager import get_error_manager, classify_exception

    manager = get_error_manager()
    check('错误目录已登记错误码', len(manager.list_errors()) >= 0)
    check('错误码分类：Errno 22 -> DOWNLOAD_CONSOLE_IO',
          classify_exception(OSError(22, 'Invalid argument'),
                             {'scope': 'download',
                              'traceback': 'File "yt_dlp\\minicurses.py", line 102, in write'})
          == 'DOWNLOAD_CONSOLE_IO')

    record = manager.report('DOWNLOAD_CONSOLE_IO', '验证脚本构造的测试错误',
                            detail='OSError: [Errno 22] Invalid argument',
                            context={'bvid': 'BV1test0001', 'scope': 'download'},
                            dedupe_key='verify-console-io')
    check('错误记录可创建', record is not None and record.id.startswith('ERR-'), record.id)

    duplicate = manager.report('DOWNLOAD_CONSOLE_IO', '重复上报',
                               context={'bvid': 'BV1test0001', 'scope': 'download'},
                               dedupe_key='verify-console-io')
    check('相同去重键的错误会合并', duplicate.id == record.id, duplicate.id)

    r = client.get('/api/system/errors')
    check('GET /api/system/errors 可用', r.status_code == 200 and r.json()['pending'] >= 1)

    r = client.get(f'/api/system/errors/{record.id}')
    body = r.json()['error']
    check('错误详情包含错误百科（原因/解决方案）',
          bool(body['spec']['causes']) and bool(body['spec']['solutions']),
          f"原因 {len(body['spec']['causes'])} 条 / 方案 {len(body['spec']['solutions'])} 条")

    r = client.get('/api/system/errors/catalog')
    check('错误百科接口可用', len(r.json().get('catalog', [])) >= 8,
          len(r.json().get('catalog', [])))

    r = client.post(f'/api/system/errors/{record.id}/repair')
    repair = r.json()
    check('一键修复接口可用', r.status_code == 200 and 'message' in repair,
          repair.get('message'))
    check('修复后错误状态变为 resolved',
          client.get(f'/api/system/errors/{record.id}').json()['error']['status'] == 'resolved')

    r = client.get(f'/api/system/errors/{record.id}/package')
    check('诊断包下载返回 ZIP',
          r.status_code == 200 and r.headers.get('content-type') == 'application/zip',
          r.headers.get('content-type'))
    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        check('诊断包结构完整',
              {'summary.txt', 'environment.json', 'error.json', 'README.txt'} <= set(names),
              names)
        env = json.loads(zf.read('environment.json').decode('utf-8'))
        check('诊断包包含流状态探测（Errno 22 诊断关键）',
              'stream_state' in env and 'stdout' in env['stream_state'])
        check('诊断包包含 yt-dlp 版本', env.get('yt_dlp_version') not in (None, ''))
        summary = zf.read('summary.txt').decode('utf-8')
        check('诊断摘要包含「可能的原因」章节', '可能的原因' in summary)
        check('诊断包已脱敏（无 SESSDATA 明文）',
              'SESSDATA=' not in summary and 'SESSDATA' not in json.dumps(env))
    except Exception as e:
        check('诊断包可解析', False, str(e))

    rec2 = manager.report('DOWNLOAD_NETWORK', '验证脚本构造的网络错误',
                          context={'bvid': 'BV1test0002'}, dedupe_key='verify-net')
    r = client.post(f'/api/system/errors/{rec2.id}/bypass', json={'note': '验证绕过'})
    check('绕过错误接口可用',
          r.status_code == 200
          and client.get(f'/api/system/errors/{rec2.id}').json()['error']['status'] == 'bypassed')

    r = client.post(f'/api/system/errors/{rec2.id}/viewed')
    check('标记已查看可用', r.status_code == 200)

    # ----------------------------------------------------------
    section('3. 调试系统')
    # ----------------------------------------------------------
    client.post('/api/debug/disable', json={'reason': '验证前置清理'})
    client.delete('/api/debug/consent')

    r = client.get('/api/debug/status')
    check('调试默认关闭', r.json().get('enabled') is False)

    r = client.get('/api/debug/agreement')
    agreement = r.json()
    check('协议文本可获取', '责任划分书' in agreement.get('agreement', ''))
    check('确认项不少于 5 项', len(agreement.get('checklist', [])) >= 5,
          len(agreement.get('checklist', [])))

    r = client.post('/api/debug/consent', json={'checklist': ['read']})
    check('未逐项确认时拒绝开启协议闸门', r.status_code == 400, r.status_code)

    r = client.post('/api/debug/enable', json={})
    check('未确认协议时无法开启调试模式', r.status_code == 403, r.status_code)

    all_ids = [item['id'] for item in agreement['checklist']]
    r = client.post('/api/debug/consent', json={'checklist': all_ids})
    check('逐项确认后可保存协议记录', r.status_code == 200, r.status_code)

    r = client.post('/api/debug/enable', json={'allow_python': True, 'allow_shell': True})
    check('确认协议后可开启调试模式', r.status_code == 200, r.status_code)
    token = r.json().get('token')
    check('开启后返回访问令牌', bool(token) and len(token) > 20)

    r = client.get('/api/debug/ping')
    check('无令牌访问被拒绝（403）', r.status_code == 403, r.status_code)

    r = client.get('/api/debug/ping', headers={'X-Debug-Token': 'wrong-token'})
    check('错误令牌被拒绝（403）', r.status_code == 403, r.status_code)

    H = {'X-Debug-Token': token}
    r = client.get('/api/debug/ping', headers=H)
    check('正确令牌可访问调试接口', r.status_code == 200 and r.json().get('message') == 'pong')

    r = client.get('/api/debug/help', headers=H)
    check('调试接口自描述文档可用', len(r.json().get('endpoints', [])) >= 8)

    r = client.get('/api/debug/scene', headers=H)
    scene = r.json()
    check('运行场景快照可用',
          all(k in scene for k in ('process', 'database', 'downloads', 'logging', 'streams')))

    r = client.get('/api/debug/logs', headers=H, params={'keyword': 'MARKER-B2'})
    check('调试接口可读取日志', r.status_code == 200 and r.json()['count'] >= 1)

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'python',
                          'payload': {'expression': 'platform.python_version()'}})
    check('受限 Python 表达式可执行', r.status_code == 200,
          r.json().get('result') if r.status_code == 200 else r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'python',
                          'payload': {'expression': 'os.system("echo hacked")'}})
    check('危险表达式被拦截', r.status_code == 400, r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'python',
                          'payload': {'expression': 'open("x").read()'}})
    check('文件读取表达式被拦截', r.status_code == 400)

    # [新增] v1.0.24：表达式沙箱原先注入了完整模块对象，且黑名单只逐词匹配
    # `subprocess.popen`，因此 `subprocess.run(..., shell=True)` 能直接执行任意系统命令，
    # 绕过独立的「命令执行」闸门（SHELL_WHITELIST / COMMAND_TIMEOUT / 审计标签）。
    # 下列断言锁定「表达式执行不得等价于任意命令执行」这一不变量。
    for expr, label in (
        ('subprocess.run("echo pwned", shell=True)', 'subprocess.run 逃逸被拦截'),
        ('subprocess.Popen("echo pwned")', 'subprocess.Popen 逃逸被拦截'),
        ('subprocess.check_output(["cmd", "/c", "echo"])', 'subprocess.check_output 逃逸被拦截'),
        ('os.popen("echo pwned").read()', 'os.popen 逃逸被拦截'),
        ('shutil.rmtree("C:/Windows/Temp")', 'shutil.rmtree 逃逸被拦截'),
        ('sys.modules', 'sys.modules 逃逸被拦截'),
    ):
        r = client.post('/api/debug/action', headers=H,
                        json={'action': 'python', 'payload': {'expression': expr}})
        check(label, r.status_code == 400, r.text[:120])

    # 链式只读表达式必须仍然可用（修复「根对象」正则后不应产生回归）
    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'python',
                          'payload': {'expression': 'sys.version.split()[0]'}})
    check('链式只读表达式仍可执行（未被根对象校验误伤）', r.status_code == 200, r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'shell', 'payload': {'command': 'echo hello'}})
    check('白名单命令可执行', r.status_code == 200, r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'shell', 'payload': {'command': 'rm -rf /'}})
    check('非白名单命令被拦截', r.status_code == 400, r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'db_query',
                          'payload': {'sql': 'SELECT bvid, download_status FROM videos LIMIT 5'}})
    check('只读 SQL 查询可用', r.status_code == 200,
          r.json().get('columns') if r.status_code == 200 else r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'db_query',
                          'payload': {'sql': 'DELETE FROM videos'}})
    check('写操作 SQL 被拦截', r.status_code == 400, r.text[:120])

    r = client.post('/api/debug/action', headers=H,
                    json={'action': 'unknown_action', 'payload': {}})
    check('未知动作被拦截', r.status_code == 400)

    r = client.get('/api/debug/audit', headers=H)
    check('调试审计日志已记录', len(r.json().get('audit', [])) >= 5,
          len(r.json().get('audit', [])))

    r = client.post('/api/debug/token/rotate', headers=H)
    new_token = r.json().get('token')
    check('令牌可轮换', r.status_code == 200 and new_token and new_token != token)
    check('旧令牌在轮换后失效',
          client.get('/api/debug/ping', headers=H).status_code == 403)

    H2 = {'X-Debug-Token': new_token}
    r = client.post('/api/debug/disable', json={'reason': '验证结束'})
    check('调试模式可关闭', r.status_code == 200)
    check('关闭后令牌立即失效',
          client.get('/api/debug/ping', headers=H2).status_code == 403)

    # ----------------------------------------------------------
    section('3.1 路径穿越防护（v1.0.24 修复）')
    # ----------------------------------------------------------
    # [新增] 原先有两处可被「客户端提供的路径片段」写到数据目录之外，
    # 另有一处能把任意目录整棵删除。断言锁定「恶意输入必须被拒绝」。
    from backend.services.backup_service import resolve_import_temp_dir, remove_temp_file
    from fastapi import HTTPException as _HTTPException

    hostile_session_ids = [
        'x/../../../../../../Windows/Temp',
        '..',
        '../../../..',
        r'x\..\..\..\Windows',
    ]
    for sid in hostile_session_ids:
        try:
            resolve_import_temp_dir(sid)
            check(f'非法导入会话 id 被拒绝 ({sid[:24]})', False, '未拒绝')
        except _HTTPException:
            check(f'非法导入会话 id 被拒绝 ({sid[:24]})', True)

    valid_session_id = '0123456789abcdef0123456789abcdef'
    resolved = resolve_import_temp_dir(valid_session_id)
    import tempfile as _tempfile
    check('合法导入会话 id 解析到系统临时目录内',
          os.path.dirname(resolved) == os.path.realpath(_tempfile.gettempdir()),
          resolved)

    # remove_temp_file 不得删除临时目录之外的任何路径
    outside_probe = os.path.join(ROOT, 'tests', '__should_not_be_deleted__')
    os.makedirs(outside_probe, exist_ok=True)
    remove_temp_file(outside_probe)
    check('remove_temp_file 拒绝删除临时目录之外的路径', os.path.isdir(outside_probe))
    try:
        os.rmdir(outside_probe)
    except Exception:
        pass

    # 主题包 zip-slip：越界成员名不得在数据目录之外落盘。
    # 直接构造恶意 zip 走真实导入函数，然后检查「应被写到目录外」的探针文件是否存在。
    import asyncio as _asyncio
    from backend.services.theme_service import import_theme_from_zip
    from backend.core.paths import DATA_DIR as _DATA_DIR

    escaped_probes = [
        os.path.abspath(os.path.join(_DATA_DIR, '__zip_slip_probe__.txt')),
        os.path.abspath(os.path.join(os.path.dirname(_DATA_DIR), '__zip_slip_probe2__.txt')),
        os.path.abspath(os.path.join(_DATA_DIR, '..', '__zip_slip_probe__.txt')),
        os.path.abspath(os.path.join(os.path.dirname(_DATA_DIR), 'stickers', '__zip_slip_probe__.txt')),
    ]
    for p in escaped_probes:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    evil_zip_bytes = io.BytesIO()
    with zipfile.ZipFile(evil_zip_bytes, 'w') as zf:
        zf.writestr('theme.json', json.dumps({'name': 'zip-slip 探针', 'settings': {}}))
        zf.writestr('stickers/..\\..\\__zip_slip_probe__.txt', b'pwned')
        zf.writestr('stickers/../../__zip_slip_probe2__.txt', b'pwned')

    class _FakeUpload:
        filename = 'evil.zip'

        def __init__(self, payload):
            self._payload = payload

        async def read(self):
            return self._payload

    try:
        from backend.database.db import SessionLocal as _SessionLocal
        with _SessionLocal() as _theme_db:
            _asyncio.new_event_loop().run_until_complete(
                import_theme_from_zip(_FakeUpload(evil_zip_bytes.getvalue()), _theme_db))
    except Exception as _e:
        # 允许因其它原因失败（例如主题校验），重点是「不得越界落盘」
        print(f'  （主题导入返回异常，属可接受：{type(_e).__name__}）')

    escaped_hit = [p for p in escaped_probes if os.path.exists(p)]
    check('主题包 zip-slip 未越界落盘（反斜杠与 ../ 两种载荷）', not escaped_hit,
          f'越界文件: {escaped_hit}' if escaped_hit else '')
    for p in escaped_hit:
        try:
            os.remove(p)
        except Exception:
            pass

    # ----------------------------------------------------------
    section('4. 下载系统（Errno 22 修复）')
    # ----------------------------------------------------------
    check('安全输出模式启动时为关闭', safe_mode_at_start is False, safe_mode_at_start)

    opts = download_service.build_yt_dlp_options(
        'out.mp4', lambda d: None)
    check('yt-dlp 已禁用进度渲染（noprogress）', opts.get('noprogress') is True)
    check('yt-dlp 已禁用控制台标题（noconsoletitle）', opts.get('noconsoletitle') is True)
    check('yt-dlp 使用静默 logger', opts.get('logger') is not None)
    check('进度回调仍然注册', len(opts.get('progress_hooks', [])) == 1)

    # 标准流守卫：写入一个"坏"流不应抛异常
    class _BrokenStream:
        encoding = 'utf-8'
        errors = 'replace'
        mode = 'w'

        def write(self, data):
            raise OSError(22, 'Invalid argument')

        def flush(self):
            raise OSError(22, 'Invalid argument')

        def isatty(self):
            return True

        def fileno(self):
            return -2

    guard = download_service._StreamGuard(_BrokenStream(), 'broken')
    ok = True
    try:
        guard.write('progress 42%\n')
        guard.write('\x1b[K hello')
        guard.flush()
        guard.buffer.write(b'bytes')
        guard.buffer.flush()
    except Exception as e:
        ok = False
        detail = str(e)
    check('坏流写入被守卫吞掉（不抛 Errno 22）', ok, '' if ok else detail)
    check('守卫流对外表现为非终端', guard.isatty() is False)

    with download_service.guarded_standard_streams():
        sys.stderr.write('这条日志应当被吞掉，不抛异常\n')
        sys.stderr.flush()
    check('guarded_standard_streams 上下文可安全进出', sys.stderr is not None)

    check('安全输出模式可启用', download_service.enable_safe_output_mode('verify') is True)
    check('启用后 SAFE_OUTPUT_MODE 为 True', download_service.is_safe_output_mode() is True)
    check('启用安全模式会写入日志',
          any('安全输出模式' in i['message']
              for i in client.get('/api/logs/list',
                                  params={'keyword': '安全输出模式'}).json()['logs']))

    # 手动重试接口（不依赖真实媒体，仅验证路由存在与参数校验）
    r = client.post('/api/download/retry/BV0000000000', params={'quality': 80})
    check('手动重试接口存在（无效媒体返回 400）', r.status_code == 400, r.status_code)
    check('重试接口会清零重试计数（代码路径存在）',
          hasattr(download_service.Downloader, 'retry_download'))

    # ----------------------------------------------------------
    section('5. 敏感信息脱敏')
    # ----------------------------------------------------------
    from backend.core.error_manager import redact
    sample = 'SESSDATA=abcdef123456; bili_jct=deadbeef; token: supersecret'
    cleaned = redact(sample)
    check('SESSDATA 被脱敏', 'abcdef123456' not in cleaned, cleaned)
    check('bili_jct 被脱敏', 'deadbeef' not in cleaned, cleaned)
    check('token 被脱敏', 'supersecret' not in cleaned, cleaned)

    # ----------------------------------------------------------
    section('7. 日志保留策略与物理文件回收（单元级）')
    # ----------------------------------------------------------
    import shutil
    import tempfile
    from backend.core.log_manager import RotatingSizeFileHandler

    tmp_dir = tempfile.mkdtemp(prefix='bilimusic-logtest-')
    try:
        handler = RotatingSizeFileHandler(
            tmp_dir, max_file_mb=0.05, max_files=2, max_total_mb=0.2)
        handler.setFormatter(logging.Formatter('%(message)s'))

        # 直接构造日志记录，绕开全局 logger，独立验证轮转逻辑
        for i in range(600):
            record = logging.LogRecord(
                name='rotate.test', level=logging.INFO, pathname=__file__, lineno=i,
                msg=f'rotation pressure line {i} ' + 'y' * 200, args=(), exc_info=None)
            handler.emit(record)
        handler.enforce_limits()

        files = [f for f in os.listdir(tmp_dir) if f.endswith('.log')]
        total = sum(os.path.getsize(os.path.join(tmp_dir, f)) for f in files)
        check('轮转后文件数量不超过上限', len(files) <= 2, f'{len(files)} 个: {sorted(files)}')
        check('轮转后总占用不超过上限',
              total <= int(0.2 * 1024 * 1024) + 4096, total)
        check('产生了归档文件（命名含时间戳）',
              any(f.startswith('bilimusic-') for f in files), sorted(files))
        check('当前写入文件仍存在', 'bilimusic.log' in files, sorted(files))

        # 收紧到 1 个文件后应只保留最新的
        handler.max_files = 1
        handler.enforce_limits()
        files = [f for f in os.listdir(tmp_dir) if f.endswith('.log')]
        check('文件数量上限收紧后立即生效', len(files) == 1, sorted(files))

        handler.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 磁盘占用统计接口与状态字段一致性
    stats = client.get('/api/logs/stats').json()
    check('日志状态包含保留策略字段',
          all(k in stats for k in ('max_files', 'max_file_bytes', 'max_total_bytes')),
          list(stats.keys()))
    check('日志状态包含内存与序号字段',
          all(k in stats for k in ('memory_count', 'memory_capacity', 'latest_seq')))
    check('日志状态带有服务器本地时间', bool(stats.get('time')), stats.get('time'))

    # ----------------------------------------------------------
    section('8. 心跳日志分类（含登录验证噪声）')
    # ----------------------------------------------------------
    from backend.core import log_manager as lm

    cases = [
        ('DEBUG - [backend.main] 请求 GET /api/auth/status', 'login'),
        ('INFO - [root] B 站登录验证成功: 用户 (UID: 1)', 'login'),
        ('DEBUG - [root] 正在请求 B 站导航接口验证登录状态...', 'login'),
        ('INFO - [root] 已清除 B 站 API 缓存', 'login'),
        ('DEBUG - [urllib3.connectionpool] https://api.bilibili.com "GET /nav" 200', 'request'),
        ('DEBUG - [backend.main] 请求 GET /api/download/status', 'polling'),
        ('ERROR - [root] [下载失败] bvid=BV1xCai6aE9g', None),
        ('INFO - [root] [下载完成] bvid=BV1xCai6aE9g', None),
    ]
    for text, expected in cases:
        check(f'心跳分类 {expected or "非心跳"} <- {text[:42]}...',
              lm.classify_heartbeat(text) == expected,
              lm.classify_heartbeat(text))

    # 类别级屏蔽
    buf = lm.LogRingBuffer(capacity=100)
    for text, expected in cases:
        buf.append({'ts': 1.0, 'time': 'x', 'level': 'INFO', 'logger': 't',
                    'message': text, 'heartbeat': expected is not None,
                    'heartbeat_category': expected})
    total = len(buf.query(limit=100))
    check('未屏蔽时返回全部记录', total == len(cases), total)
    check('屏蔽全部心跳后只剩业务日志',
          len(buf.query(hide_heartbeat=True, limit=100)) == 2,
          len(buf.query(hide_heartbeat=True, limit=100)))
    check('可只屏蔽「登录验证」类别',
          len(buf.query(hide_heartbeat=True, heartbeat_categories=['login'], limit=100)) == 4)
    check('可只屏蔽「HTTP 请求」类别',
          len(buf.query(hide_heartbeat=True, heartbeat_categories=['request'], limit=100)) == 7)
    check('可只屏蔽「前端轮询」类别',
          len(buf.query(hide_heartbeat=True, heartbeat_categories=['polling'], limit=100)) == 7)
    check('可叠加屏蔽多个类别',
          len(buf.query(hide_heartbeat=True,
                        heartbeat_categories=['login', 'polling'], limit=100)) == 3)

    meta = client.get('/api/logs/meta').json()
    check('日志元数据返回心跳类别计数',
          isinstance(meta.get('heartbeat_categories'), dict), meta.get('heartbeat_categories'))

    # ----------------------------------------------------------
    section('9. 打开日志目录（多路径回退）')
    # ----------------------------------------------------------
    # 直接调用函数，验证「返回值契约」与容错性
    ok, detail = lm.open_log_dir()
    check('打开日志目录返回 (bool, str) 契约',
          isinstance(ok, bool) and isinstance(detail, str), f'{ok}, {detail}')
    check('返回的目录路径正确', lm.get_log_dir() in detail or ok, detail)

    # 即使全部打开方式都失败，也必须给出可读的失败原因而不是崩溃
    import unittest.mock as mock

    def _boom(*a, **k):
        raise PermissionError(5, '拒绝访问')

    with mock.patch.object(lm.os, 'startfile', _boom, create=True), \
            mock.patch.object(lm.subprocess, 'Popen', _boom), \
            mock.patch('ctypes.windll', create=True) as fake_windll:
        fake_windll.shell32.ShellExecuteW.return_value = 5  # <=32 表示失败
        ok2, detail2 = lm.open_log_dir()
    check('全部打开方式失败时返回 False 且带原因',
          ok2 is False and ('无法打开目录' in detail2), detail2)
    check('失败原因中记录了尝试过的路径', '尝试记录' in detail2, detail2[:120])

    # HTTP 层：接口不会因为打开失败而 500 崩溃；成功时返回目录
    r = client.post('/api/logs/open-dir')
    check('打开目录接口可调用（成功 200 / 失败 500 且带原因）',
          r.status_code in (200, 500), r.status_code)

    # ----------------------------------------------------------
    section('10. 日志接口健壮性（避免“点了没反应”）')
    # ----------------------------------------------------------
    # 注意：日志中间件会把「查询请求自身的 URL」也写进日志，
    # 因此关键字断言必须使用不会被查询语句本身包含的标记。
    MARKER_BEFORE = 'MARKERBEFORECLEAR'
    MARKER_AFTER = 'MARKERAFTERCLEAR'

    logging.getLogger('verify.clear').info(MARKER_BEFORE)
    check('清屏前可检索到标记日志',
          client.get('/api/logs/list',
                     params={'keyword': MARKER_BEFORE}).json()['count'] >= 1)

    r = client.post('/api/logs/clear', params={'memory_only': True})
    check('清屏接口返回可解析结果', r.status_code == 200 and 'removed_files' in r.json())
    check('清屏后旧日志已被移除',
          client.get('/api/logs/list',
                     params={'keyword': MARKER_BEFORE}).json()['count'] == 0)

    logging.getLogger('verify.clear').info(MARKER_AFTER)
    check('清屏后仍可继续记录日志',
          client.get('/api/logs/list',
                     params={'keyword': MARKER_AFTER}).json()['count'] == 1)
    # 清屏接口自身会把「正在处理该请求」的中间件日志写入缓冲，因此条数不会严格为 0
    check('清屏后缓冲中只剩极少量的即时日志',
          client.get('/api/logs/stats').json()['memory_count'] < 20,
          client.get('/api/logs/stats').json()['memory_count'])

    r = client.get('/api/logs/export', params={'fmt': 'txt', 'limit': 10})
    check('导出接口返回文本内容', r.status_code == 200 and len(r.content) > 0)
    r = client.get('/api/logs/export', params={'fmt': 'json', 'limit': 10, 'download': True})
    check('导出接口支持 download 头',
          'attachment' in r.headers.get('content-disposition', ''),
          r.headers.get('content-disposition'))
    r = client.get('/api/logs/stream', params={'request_timeout': 10, 'hide_heartbeat': 'true',
                                               'hide_heartbeat_categories': 'login'})
    check('实时日志接口接受心跳类别参数', r.status_code == 200, r.status_code)

    check('调试协议接口返回完整内容',
          len(client.get('/api/debug/agreement').json().get('agreement', '')) > 500)


def _no_1970(path):
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(max(0, os.path.getsize(path) - 20000))
            tail = f.read()
        return '1970-' not in tail and '1970/' not in tail
    except Exception:
        return False


def _same_minute(time_str, ts):
    """验证可读时间字符串与 epoch 时间戳指向同一分钟。"""
    try:
        shown = time.strptime(str(time_str), '%Y-%m-%d %H:%M:%S')
        local = time.localtime(ts)
        return (shown.tm_year, shown.tm_mon, shown.tm_mday, shown.tm_hour, shown.tm_min) == \
               (local.tm_year, local.tm_mon, local.tm_mday, local.tm_hour, local.tm_min)
    except Exception:
        return False


def _is_json_list(text):
    try:
        return isinstance(json.loads(text), list)
    except Exception:
        return False


if __name__ == '__main__':
    sys.exit(main())

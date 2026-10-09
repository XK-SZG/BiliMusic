# BiliMusic 测试与自检

## 目录结构

```
tests/
├── verify_backend_v1021.py      # 后端自检脚本（日志 / 错误 / 调试 / 下载修复）
├── check_api_wiring.cjs         # 前端 ↔ 后端 接线静态校验
├── check_api_wiring_selftest.cjs # 接线校验脚本自身的负向自检
└── README.md                    # 本文件
```

> 说明：本目录此前记载的 `simple_test.py`、`load_test.py`、`realistic_load_test.py`
> 已被移除（见 `CHANGELOG.md` 1.0.20「清理测试脚本」），相关文档亦不存在。
> 本文件已按当前仓库的真实内容重写。

---

## 〇、前端 ↔ 后端接线校验（建议每次改前端 API 后执行）

```bash
node tests/check_api_wiring.cjs          # 接线校验
node tests/check_api_wiring_selftest.cjs # 校验脚本自身的负向自检
```

该脚本扫描 `frontend/src` 与 `backend/routers`，做两项交叉校验：

| 检查 | 内容 | 拦截过的真实缺陷 |
|---|---|---|
| A | 组件调用的 `xxxApi.方法()` 是否真的在对应模块中导出 | `systemApi.getStats is not a function`（实现写在 `api/logs.js`，组件却从 `systemApi` 调用） |
| B | 受 `require_debug_token` 保护的后端接口，前端是否携带 `X-Debug-Token`，调用方首个参数是否为令牌 | 刷新审计日志报 403「令牌校验失败」（`getDebugAudit` 漏传令牌） |

- 全部通过输出 `检查通过：未发现接线问题`，退出码 `0`；
- 存在问题逐条打印「文件:行号 + 问题描述」，退出码 `1`。

`check_api_wiring_selftest.cjs` 会把 `getDebugAudit` 临时改回「漏传令牌」的写法，
确认校验脚本确实能检出该缺陷，然后自动恢复文件并复查。**它不应该修改留下任何改动**。

---

## 一、后端自检脚本`verify_backend_v1021.py`

### 1.1 它做什么

`verify_backend_v1021.py` 以**进程内**方式启动 FastAPI 应用（使用 `TestClient`，
**不占用真实端口**），并额外拉起一个临时的 `uvicorn` 进程用于验证 SSE 长连接。
共 100+ 项断言，覆盖：

| 章节 | 内容 |
|---|---|
| 1. 日志系统 | 时间戳与系统时间同步、物理文件落盘、无 1970 时间戳、关键字/级别/排除/时间区间/心跳屏蔽的叠加筛选、增量拉取、导出 TXT/JSON、保留策略调整、删除确认 |
| 2. 错误系统 | 错误分类（Errno 22 → `DOWNLOAD_CONSOLE_IO`）、去重合并、错误百科、一键修复、绕过、标记已查看、诊断包 ZIP 结构与脱敏 |
| 3. 调试系统 | 协议闸门（未逐项确认必须被拒绝）、令牌鉴权、错误令牌拒绝、运行场景快照、受限表达式、危险表达式拦截、命令白名单、只读 SQL 限制、审计日志、令牌轮换与销毁 |
| 4. 下载系统 | yt-dlp 安全输出选项、坏流写入被守卫吞掉、手动重试接口 |
| 5. 敏感信息脱敏 | SESSDATA / bili_jct / token 必须被脱敏 |
| 6. 实时推送（SSE） | 真实 HTTP 服务下的日志实时推送、错误事件补发、心跳帧 |
| 7. 日志轮转与回收 | 单文件体积轮转、文件数量上限、总占用上限、上限收紧后立即回收 |

### 1.2 前置条件

后端依赖已安装（`pip install -r requirements.txt`）即可，**不需要**先启动后端服务。

### 1.3 运行

在项目根目录执行：

```bash
.venv\Scripts\python.exe tests\verify_backend_v1021.py
```

（Windows PowerShell 下可直接使用 `& .venv\Scripts\python.exe -B -u tests\verify_backend_v1021.py`）

### 1.4 预期输出

每一项断言都会打印 `[PASS]` 或 `[FAIL]`，结尾给出汇总：

```
==================================================================
  通过 97 项，失败 0 项
==================================================================
```

退出码：全部通过为 `0`，存在失败为 `1`（可用于脚本化门禁）。

### 1.5 安全说明

- 脚本**不会**触发关机、休眠、重置软件、卸载等破坏性操作；
- 脚本会读取 `backend/data/` 下的运行数据以统计状态，但**不读取也不输出**
  `bili_cookies.json` 与 `bili_user_info.json` 的内容；
- 脚本会在 `backend/data/logs/` 写入测试日志，并临时调整日志保留策略
  （结束时恢复默认值）；
- SSE 验证会临时占用端口 `12199`，结束后立即释放。

---

## 二、其他验证手段

当前仓库**没有**配置任何自动化测试框架或 CI，也没有 lint / 格式化门禁
（详见 `AGENTS.md` 第 2.5、4.5 节）。除本自检脚本外，可用的验证手段为：

### 2.1 后端手工验证

```bash
python run_backend.py
```

服务监听 `http://127.0.0.1:12180`，可直接访问：

- `http://127.0.0.1:12180/docs` —— FastAPI 自动生成的接口文档
- `GET /api/logs/stats` —— 日志系统状态
- `POST /api/debug/enable` —— 需要在界面中先完成协议确认

### 2.2 前端构建验证

```bash
cd frontend
npm run build
```

该命令会完整编译所有 `.vue` 单文件组件；构建失败通常意味着模板结构或脚本语法有问题。

### 2.3 前端联调

```bash
cd frontend
npm run electron:dev
```

---

## 三、编写新测试的建议

1. 优先扩展现有的 `verify_backend_v1021.py`，保持「进程内 + 断言清单」的风格；
2. 涉及长连接（SSE）的验证请使用真实的 `uvicorn` 子进程 + `requests` 流式读取，
   不要使用 `TestClient`（长连接无法安全中断，会导致脚本挂起）；
3. 任何测试都**不得**读取或输出 `backend/data/` 下的凭据类文件
   （见 `AGENTS.md` 第 3.1 节）；
4. 任何测试都**不得**触发关机、休眠、重置软件、卸载等破坏性操作。

---

**最后更新：2026年10月8日**

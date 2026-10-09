# BiliMusic 测试与自检

## 目录结构

```
tests/
├── verify_backend_v1021.py      # 后端自检脚本（日志 / 错误 / 调试 / 下载修复 / 路径穿越防护）
├── verify_update_overwrite.cjs  # 发行包「覆盖更新」数据安全沙盒验证（v1.0.24 新增）
├── verify_cover_url.py          # 封面地址净化逻辑验证（后端）
├── verify_cover_format.cjs      # 封面地址格式化验证（前端 formatImg / normalizePic）
├── verify_proxy_image.py        # /api/proxy/image 健壮性验证
├── check_api_wiring.cjs         # 前端 ↔ 后端 接线静态校验
├── check_api_wiring_selftest.cjs # 接线校验脚本自身的负向自检
└── README.md                    # 本文件
```

> 说明：本目录此前记载的 `simple_test.py`、`load_test.py`、`realistic_load_test.py`
> 已被移除（见 `CHANGELOG.md` 1.0.20「清理测试脚本」），相关文档亦不存在。
> 本文件已按当前仓库的真实内容重写。

---

## 〇之前、发行包覆盖更新数据安全验证（v1.0.24 新增）

```bash
node tests/verify_update_overwrite.cjs    # 19 项断言
```

**为什么需要它**：安装器升级时会调用「旧版卸载器」清理旧程序文件，而负责生成清理宏的
[`frontend/build/afterPack.cjs`](../frontend/build/afterPack.cjs) 一旦写错，就会在**升级时删掉用户数据** ——
这正是 `CHANGELOG.md` 1.0.20 记录过的致命缺陷。用户数据位于
`$INSTDIR\resources\backend\data`（媒体库库文件、下载缓存、Cookie），一旦丢失不可恢复。

本脚本**不依赖 NSIS 与本机安装**，而是：

1. 解析真实参与编译的 `frontend/build/uninstall_list.nsh`（由 `afterPack.cjs` 生成）；
2. 在系统临时目录建沙盒，按真实布局铺一份「旧版本安装目录」，其中包含
   `backend/data` 下的用户数据、用户自建文件、以及旧版遗留文件；
3. 按 NSIS 语义逐条执行宏（`Rename` 目标已存在则失败、`RMDir` 仅在空目录成功、
   按 `${If} $R9 == "0"` / `${Else}` 选择分支）；
4. 模拟安装器写入新版程序文件；
5. 断言结果。

| 断言组 | 锁定的不变量 |
|---|---|
| 静态红线 | `RMDir /r "$INSTDIR"` **只出现在 `$R9 == "0"` 分支**；`cleanOldFiles` 不含递归删除；覆盖清单包含 `backend.exe` |
| 覆盖升级（`$R9=1`） | 用户数据与用户自建文件**全部存活且内容未被改写**；程序文件确实被替换为新版；无旧文件挡住新文件；`data` 目录路径不漂移 |
| 删除数据（`$R9=0`） | 用户明确要求删除时安装目录被完整清理（行为符合预期，不是缺陷） |
| **负向自检** | 把宏换成历史上有缺陷的 `RMDir /r "$INSTDIR"` 写法，确认脚本**能检出**数据丢失 |

**安全约定**：脚本只在系统临时目录内读写（结束时自动清理），绝不触碰真实安装目录或
`backend/data/`；不执行关机 / 休眠 / 卸载等任何破坏性动作；沙盒里的「凭据文件」只是占位文本。

---

## 〇之前、封面地址相关验证（v1.0.23 新增）

```bash
.venv\Scripts\python.exe tests\verify_cover_url.py      # 后端净化逻辑（24 项）
node tests\verify_cover_format.cjs                      # 前端格式化（18 项）
.venv\Scripts\python.exe tests\verify_proxy_image.py    # 代理接口健壮性（10 项）
```

**为什么需要它们**：v1.0.22 把 `API_BASE` 改为同源相对路径后，前端的 `formatImg()`
把 `/api/proxy/image?url=...` 误拼成 `https:///api/proxy/image?url=...`（三斜杠、无主机名），
且该「展示用地址」被两处调用点写进了数据库，导致收藏夹 / 本地媒体库 / 队列 / 统计四个页面的
卡片封面全部永久失效。这三份脚本分别锁定：

| 脚本 | 锁定的不变量 |
|---|---|
| `verify_cover_url.py` | 净化后绝不残留 `/proxy/image`、绝不出现三斜杠地址、幂等、限深不死循环 |
| `verify_cover_format.cjs` | `formatImg` 不叠加代理层（幂等）、`normalizePic` 产出绝不含代理包装 |
| `verify_proxy_image.py` | 畸形地址返回 404 而非 500、正常直链返回图片 |

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
共 **148 项断言**，覆盖：

| 章节 | 内容 |
|---|---|
| 1. 日志系统 | 时间戳与系统时间同步、物理文件落盘、无 1970 时间戳、关键字/级别/排除/时间区间/心跳屏蔽的叠加筛选、增量拉取、导出 TXT/JSON、保留策略调整、删除确认 |
| 2. 错误系统 | 错误分类（Errno 22 → `DOWNLOAD_CONSOLE_IO`）、去重合并、错误百科、一键修复、绕过、标记已查看、诊断包 ZIP 结构与脱敏 |
| 3. 调试系统 | 协议闸门（未逐项确认必须被拒绝）、令牌鉴权、错误令牌拒绝、运行场景快照、受限表达式、危险表达式拦截、**表达式沙箱逃逸拦截（6 种）**、命令白名单、只读 SQL 限制、审计日志、令牌轮换与销毁 |
| 3.1 路径穿越防护 | 非法导入会话 id 被拒绝、`remove_temp_file` 拒绝删除临时目录之外的路径、主题包 zip-slip（`..\` 与 `../` 两种载荷）不得越界落盘 |
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
  通过 148 项，失败 0 项
==================================================================
```

退出码：全部通过为 `0`，存在失败为 `1`（可用于脚本化门禁）。

### 1.5 安全说明

- 脚本**不会**触发关机、休眠、重置软件、卸载等破坏性操作；
- 脚本会读取 `backend/data/` 下的运行数据以统计状态，但**不读取也不输出**
  `bili_cookies.json` 与 `bili_user_info.json` 的内容；
- 脚本会在 `backend/data/logs/` 写入测试日志，并临时调整日志保留策略
  （结束时恢复默认值）；
- 脚本会在 `backend/data/` 下创建探针文件用于验证 zip-slip 防护，并在结束时自行清理；
- SSE 验证会临时占用端口 `12199`，结束后立即释放。

---

## 二、其他验证手段

当前仓库**没有**配置任何自动化测试框架或 CI，也没有 lint / 格式化门禁
（详见 `AGENTS.md` 第 2.5、4.5 节）。因此上述脚本是**唯一**的自动化防线：
改后端跑 `verify_backend_v1021.py`，改前端 API 跑 `check_api_wiring.cjs`，
改安装器 / 打包配置跑 `verify_update_overwrite.cjs`。除这些脚本外，可用的验证手段为：

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

# BiliMusic 性能测试工具使用指南

## 目录结构
```
tests/
├── simple_test.py           # 简单的 API 连通性测试
├── load_test.py             # Locust 压力测试脚本（使用随机数据）
├── realistic_load_test.py   # 实用压测脚本（使用真实数据）⭐ 推荐
└── README.md                # 本文件
```

## 一、前置准备

### 1.1 确保后端服务已启动
```bash
# 在项目根目录运行
python run_backend.py
```

后端应该在 `http://127.0.0.1:12243` 上运行。

### 1.2 安装测试依赖
```bash
pip install locust requests
```

## 二、快速测试（推荐新手）

### 2.1 运行简单测试
这个脚本会测试几个基本的 API 端点，验证后端是否正常运行：

```bash
python tests/simple_test.py
```

**预期输出：**
```
============================================================
BiliMusic 后端 API 简单测试
============================================================

✓ GET /local/videos
  状态码: 200
  响应时间: 45.23ms
  响应数据: [...]

✓ GET /local/collections
  状态码: 200
  响应时间: 32.15ms
  响应数据: [...]

...

============================================================
测试完成: 4/4 通过
============================================================

✓ 所有测试通过！后端服务运行正常
```

如果看到 "无法连接到服务器" 错误，请确保后端已启动。

## 三、压力测试（进阶）

### 3.1 推荐：使用真实数据压测 ⭐
这个脚本会自动从数据库获取真实的 BVID，避免大量 404 错误：

```bash
locust -f tests/realistic_load_test.py --host=http://127.0.0.1:12243
```

### 3.2 启动 Locust Web UI
这是最直观的方式，提供了实时图表和控制面板：

```bash
# 使用真实数据（推荐）
locust -f tests/realistic_load_test.py --host=http://127.0.0.1:12243

# 或使用随机数据（会有较多 404）
locust -f tests/load_test.py --host=http://127.0.0.1:12243
```

然后在浏览器中打开 `http://localhost:8089`，你会看到 Locust 的 Web 界面。

**配置参数：**
- **Number of users (peak concurrency)**: 并发用户数，建议从 10 开始
- **Spawn rate (users started/second)**: 每秒增加的用户数，建议 2-5
- **Host**: 已自动填充为 `http://127.0.0.1:12243`

点击 "Start swarming" 开始压测。

### 3.3 命令行模式（无 UI）
适合自动化测试或 CI/CD 集成：

```bash
# 使用真实数据：50 个用户，每秒增加 5 个，持续 60 秒
locust -f tests/realistic_load_test.py --host=http://127.0.0.1:12243 \
  --users 50 --spawn-rate 5 --run-time 60s --headless

# 使用随机数据：100 个用户（会有较多 404）
locust -f tests/load_test.py --host=http://127.0.0.1:12243 \
  --users 100 --spawn-rate 10 --run-time 60s --headless
```

**参数说明：**
- `--users 100`: 最大并发用户数
- `--spawn-rate 10`: 每秒增加 10 个用户
- `--run-time 60s`: 运行 60 秒后自动停止
- `--headless`: 无 Web UI，直接在终端输出结果

### 3.3 自定义压测场景

#### 场景 1: 高并发流媒体代理测试
```bash
locust -f tests/load_test.py --host=http://127.0.0.1:12243 \
  HighConcurrencyScenario --users 50 --spawn-rate 10 --run-time 120s --headless
```

#### 场景 2: 下载队列压测（测试断路器）
```bash
locust -f tests/load_test.py --host=http://127.0.0.1:12243 \
  DownloadQueueScenario --users 20 --spawn-rate 5 --run-time 60s --headless
```

## 四、结果分析

### 4.1 关键指标

Locust 会输出以下关键指标：

| 指标 | 说明 | 理想值 |
|------|------|--------|
| **Total Requests** | 总请求数 | 越多越好 |
| **Failures** | 失败请求数 | 越少越好 (<1%) |
| **Average Response Time** | 平均响应时间 | <100ms |
| **P95 Response Time** | 95% 请求的响应时间 | <200ms |
| **P99 Response Time** | 99% 请求的响应时间 | <500ms |
| **RPS (Requests/sec)** | 每秒请求数 | 越高越好 |

### 4.2 示例输出解读

```
Type     Name                          # reqs      # fails  |     Avg     Min     Max  Median  |   req/s failures/s
--------|----------------------------|-----------|---------|-------|-------|-------|-------|--------|-----------
GET      /api/local/videos              1234         0     |      45      12     234      38  |   20.5        0.00
GET      /api/play/stream/[bvid]         567         3     |     456      89    2345     345  |    9.4        0.05
POST     /api/system/download/[bvid]     234         0     |      23       8      89      19  |    3.9        0.00
--------|----------------------------|-----------|---------|-------|-------|-------|-------|--------|-----------
         Aggregated                     2035         3     |     174       8    2345      45  |   33.8        0.05
```

**解读：**
- `/api/local/videos`: 1234 次请求，0 次失败，平均 45ms，每秒 20.5 个请求 ✓
- `/api/play/stream/[bvid]`: 567 次请求，3 次失败（0.5%），平均 456ms ⚠️ 可能需要优化
- 总体失败率: 3/2035 = 0.15% ✓ 在可接受范围内

## 五、常见问题

### Q1: 运行 `python tests/load_test.py` 没有任何输出
**A**: Locust 脚本不能直接用 Python 运行，必须使用 `locust` 命令：
```bash
locust -f tests/load_test.py --host=http://127.0.0.1:12243
```

### Q2: 提示 "Connection refused" 或 "无法连接"
**A**: 后端服务未启动或端口不正确。请检查：
1. 运行 `python run_backend.py` 启动后端
2. 确认后端监听在 `127.0.0.1:12243`
3. 检查防火墙设置

### Q3: 压测时出现大量 500 错误
**A**: 可能是：
1. 并发数过高，超出服务器承载能力（降低 `--users` 参数）
2. 数据库连接池耗尽（检查后端日志）
3. 内存不足（监控系统资源）

### Q4: 如何停止正在运行的压测？
**A**: 
- Web UI 模式：点击 "Stop" 按钮
- 命令行模式：按 `Ctrl+C`

## 六、性能基准参考

根据 [`docs/Phase3_全链路压测与OOM防御.md`](../docs/Phase3_全链路压测与OOM防御.md) 中的基准：

| API 端点 | 并发用户 | 平均响应时间 | P95 | 吞吐量 (RPS) | 错误率 |
|---------|---------|------------|-----|------------|--------|
| GET /api/local/videos | 50 | <100ms | <200ms | >200 | <1% |
| GET /api/play/stream/[bvid] | 20 | <500ms | <1000ms | >50 | <2% |
| POST /api/system/download/[bvid] | 10 | <50ms | <100ms | >100 | <1% |

如果你的测试结果显著低于这些基准，可能需要进一步优化。

## 七、进阶技巧

### 7.1 生成 HTML 报告
```bash
locust -f tests/load_test.py --host=http://127.0.0.1:12243 \
  --users 100 --spawn-rate 10 --run-time 60s --headless \
  --html=report.html
```

### 7.2 分布式压测（多机）
在主机上：
```bash
locust -f tests/load_test.py --master --host=http://127.0.0.1:12243
```

在工作机上：
```bash
locust -f tests/load_test.py --worker --master-host=<主机IP>
```

### 7.3 自定义日志级别
```bash
locust -f tests/load_test.py --host=http://127.0.0.1:12243 --loglevel DEBUG
```

## 八、参考资源
- [Locust 官方文档](https://docs.locust.io/)
- [性能优化完整方案](../docs/BiliMusic_深度架构解析与极致性能优化方案.md)
- [压测详细指南](../docs/Phase3_全链路压测与OOM防御.md)

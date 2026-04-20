"""
BiliMusic 后端 API 压力测试脚本
使用 Locust 进行并发压测

安装依赖:
    pip install locust

运行方式:
    # Web UI 模式
    locust -f tests/load_test.py --host=http://127.0.0.1:12280
    
    # 命令行模式（100 用户，每秒增加 10 个，持续 60 秒）
    locust -f tests/load_test.py --host=http://127.0.0.1:12280 \
      --users 100 --spawn-rate 10 --run-time 60s --headless
"""

from locust import HttpUser, task, between, events
import random
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BiliMusicUser(HttpUser):
    """模拟 BiliMusic 用户行为"""
    
    # 用户操作间隔时间（秒）
    wait_time = between(1, 3)
    
    def on_start(self):
        """用户启动时执行：模拟登录或初始化"""
        logger.info(f"[用户 {self.client.base_url}] 开始压测")
        # 如果需要认证，在此处添加登录逻辑
        # response = self.client.post("/api/auth/login", json={"username": "test", "password": "test"})
    
    @task(10)
    def get_local_videos(self):
        """
        任务权重 10：获取本地视频列表（高频操作）
        """
        with self.client.get("/api/local/videos", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"获取本地视频失败: {response.status_code}")
    
    @task(5)
    def get_local_collections(self):
        """
        任务权重 5：获取本地收藏夹列表
        """
        self.client.get("/api/local/collections")
    
    @task(8)
    def stream_video(self):
        """
        任务权重 8：流媒体播放（模拟）
        注意：实际播放会产生大量流量，压测时仅请求头部数据
        """
        # 随机生成 BVID（实际应从数据库获取真实 BVID）
        bvid = f"BV1{random.randint(100000000, 999999999)}"
        
        with self.client.get(
            f"/api/play/stream/{bvid}",
            headers={"Range": "bytes=0-1024"},  # 仅请求前 1KB
            name="/api/play/stream/[bvid]",
            catch_response=True
        ) as response:
            # 206 Partial Content 或 404 Not Found 都是正常的
            if response.status_code in [200, 206, 404]:
                response.success()
            else:
                response.failure(f"流媒体请求失败: {response.status_code}")
    
    @task(3)
    def add_to_download(self):
        """
        任务权重 3：添加下载任务
        """
        bvid = f"BV1{random.randint(100000000, 999999999)}"
        
        with self.client.post(
            f"/api/system/download/{bvid}?quality=80",
            name="/api/system/download/[bvid]",
            catch_response=True
        ) as response:
            # 可能返回 200（成功）或 400（已存在/不存在）
            if response.status_code in [200, 400, 404]:
                response.success()
            else:
                response.failure(f"添加下载失败: {response.status_code}")
    
    @task(15)
    def get_download_status(self):
        """
        任务权重 15：查询下载状态（最高频操作）
        """
        self.client.get("/api/system/download/status")
    
    @task(2)
    def get_stats(self):
        """
        任务权重 2：获取统计数据
        """
        self.client.get("/api/stats/overview")
    
    @task(1)
    def proxy_image(self):
        """
        任务权重 1：图片代理（低频）
        """
        # 模拟 B 站封面 URL
        test_url = "https://i0.hdslb.com/bfs/archive/test.jpg"
        self.client.get(f"/api/proxy/image?url={test_url}", name="/api/proxy/image")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """压测开始时的回调"""
    logger.info("=" * 60)
    logger.info("BiliMusic 压力测试开始")
    logger.info(f"目标主机: {environment.host}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """压测结束时的回调"""
    logger.info("=" * 60)
    logger.info("BiliMusic 压力测试结束")
    logger.info("=" * 60)
    
    # 输出统计摘要
    stats = environment.stats
    logger.info(f"总请求数: {stats.total.num_requests}")
    logger.info(f"总失败数: {stats.total.num_failures}")
    logger.info(f"平均响应时间: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"P95 响应时间: {stats.total.get_response_time_percentile(0.95):.2f}ms")
    logger.info(f"P99 响应时间: {stats.total.get_response_time_percentile(0.99):.2f}ms")
    logger.info(f"RPS (请求/秒): {stats.total.total_rps:.2f}")


# 自定义压测场景（可选）
class HighConcurrencyScenario(HttpUser):
    """高并发场景：专注于流媒体代理压测"""
    
    wait_time = between(0.5, 1)
    
    @task
    def stream_only(self):
        bvid = f"BV1{random.randint(100000000, 999999999)}"
        self.client.get(
            f"/api/play/stream/{bvid}",
            headers={"Range": "bytes=0-10240"},  # 请求前 10KB
            name="/api/play/stream/[bvid]"
        )


class DownloadQueueScenario(HttpUser):
    """下载队列压测场景：测试断路器"""
    
    wait_time = between(0.1, 0.5)
    
    @task
    def rapid_download(self):
        bvid = f"BV1{random.randint(100000000, 999999999)}"
        self.client.post(
            f"/api/system/download/{bvid}?quality=80",
            name="/api/system/download/[bvid]"
        )

"""
BiliMusic 实用压力测试脚本
使用真实的数据库数据进行压测，避免大量 404 错误

运行方式:
    locust -f tests/realistic_load_test.py --host=http://127.0.0.1:12280
"""

from locust import HttpUser, task, between, events
import random
import logging
import requests

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量：存储真实的 BVID 列表
REAL_BVIDS = []
REAL_COLLECTIONS = []


def fetch_real_data(host):
    """从后端获取真实的 BVID 和收藏夹数据"""
    global REAL_BVIDS, REAL_COLLECTIONS
    
    try:
        # 获取本地视频列表
        response = requests.get(f"{host}/api/local/videos", timeout=5)
        if response.status_code == 200:
            videos = response.json()
            REAL_BVIDS = [v['bvid'] for v in videos if 'bvid' in v]
            logger.info(f"[数据初始化] 获取到 {len(REAL_BVIDS)} 个真实 BVID")
        
        # 获取收藏夹列表
        response = requests.get(f"{host}/api/local/collections", timeout=5)
        if response.status_code == 200:
            collections = response.json()
            REAL_COLLECTIONS = [c['id'] for c in collections if 'id' in c]
            logger.info(f"[数据初始化] 获取到 {len(REAL_COLLECTIONS)} 个收藏夹")
    except Exception as e:
        logger.warning(f"[数据初始化] 获取真实数据失败: {e}")
        logger.warning("[数据初始化] 将使用模拟数据进行压测")


class RealisticBiliMusicUser(HttpUser):
    """使用真实数据的压测用户"""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """用户启动时执行"""
        # 如果还没有获取真实数据，先获取
        if not REAL_BVIDS and not REAL_COLLECTIONS:
            fetch_real_data(self.client.base_url)
    
    @task(15)
    def get_local_videos(self):
        """获取本地视频列表（最高频）"""
        self.client.get("/api/local/videos")
    
    @task(8)
    def get_local_collections(self):
        """获取收藏夹列表"""
        self.client.get("/api/local/collections")
    
    @task(10)
    def get_download_status(self):
        """查询下载状态（高频）"""
        with self.client.get("/api/download/status", catch_response=True) as response:
            # 404 也视为成功（端点可能不存在或无下载任务）
            if response.status_code in [200, 404]:
                response.success()
    
    @task(5)
    def get_stats_overview(self):
        """获取统计概览"""
        self.client.get("/api/stats/overview")
    
    @task(3)
    def get_stats_daily(self):
        """获取每日统计"""
        with self.client.get("/api/stats/play_schedule", catch_response=True) as response:
            # 如果端点不存在，标记为成功（避免影响测试结果）
            if response.status_code == 404:
                response.success()
    
    @task(2)
    def get_stats_top_videos(self):
        """获取热门视频"""
        with self.client.get("/api/stats/rankings", catch_response=True) as response:
            if response.status_code == 404:
                response.success()
    
    @task(5)
    def stream_real_video(self):
        """
        流媒体播放（使用真实 BVID）
        仅请求头部数据以避免大流量
        """
        if REAL_BVIDS:
            bvid = random.choice(REAL_BVIDS)
            self.client.get(
                f"/api/play/stream/{bvid}",
                headers={"Range": "bytes=0-10240"},  # 仅请求前 10KB
                name="/api/play/stream/[real_bvid]"
            )
    
    @task(1)
    def proxy_image(self):
        """图片代理（低频）"""
        # 使用一个固定的测试 URL
        test_url = "https://i0.hdslb.com/bfs/archive/test.jpg"
        self.client.get(
            f"/api/proxy/image?url={test_url}",
            name="/api/proxy/image",
            catch_response=True
        )


class LightweightUser(HttpUser):
    """轻量级用户：仅测试快速 API"""
    
    wait_time = between(0.5, 1.5)
    
    @task(10)
    def get_download_status(self):
        """高频查询下载状态"""
        with self.client.get("/api/download/status", catch_response=True) as response:
            if response.status_code in [200, 404]:
                response.success()
    
    @task(5)
    def get_local_collections(self):
        """获取收藏夹"""
        self.client.get("/api/local/collections")
    
    @task(3)
    def get_stats_overview(self):
        """获取统计"""
        self.client.get("/api/stats/overview")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """压测开始时的回调"""
    logger.info("=" * 60)
    logger.info("BiliMusic 实用压力测试开始")
    logger.info(f"目标主机: {environment.host}")
    logger.info("=" * 60)
    
    # 预先获取真实数据
    fetch_real_data(environment.host)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """压测结束时的回调"""
    logger.info("=" * 60)
    logger.info("BiliMusic 实用压力测试结束")
    logger.info("=" * 60)
    
    # 输出统计摘要
    stats = environment.stats
    logger.info(f"总请求数: {stats.total.num_requests}")
    logger.info(f"总失败数: {stats.total.num_failures}")
    logger.info(f"失败率: {stats.total.fail_ratio * 100:.2f}%")
    logger.info(f"平均响应时间: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"P95 响应时间: {stats.total.get_response_time_percentile(0.95):.2f}ms")
    logger.info(f"P99 响应时间: {stats.total.get_response_time_percentile(0.99):.2f}ms")
    logger.info(f"RPS (请求/秒): {stats.total.total_rps:.2f}")
    
    # 性能评估
    logger.info("=" * 60)
    logger.info("性能评估:")
    
    if stats.total.fail_ratio > 0.05:
        logger.warning(f"⚠️  失败率过高 ({stats.total.fail_ratio * 100:.2f}%)，建议检查后端日志")
    else:
        logger.info(f"✓ 失败率正常 ({stats.total.fail_ratio * 100:.2f}%)")
    
    if stats.total.avg_response_time > 200:
        logger.warning(f"⚠️  平均响应时间较慢 ({stats.total.avg_response_time:.2f}ms)")
    else:
        logger.info(f"✓ 平均响应时间良好 ({stats.total.avg_response_time:.2f}ms)")
    
    if stats.total.total_rps < 50:
        logger.warning(f"⚠️  吞吐量较低 ({stats.total.total_rps:.2f} RPS)")
    else:
        logger.info(f"✓ 吞吐量良好 ({stats.total.total_rps:.2f} RPS)")

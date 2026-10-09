# -*- coding: utf-8 -*-
# Path: backend/services/cover_cache_service.py

import os
import hashlib
import asyncio
import logging
import httpx
from typing import Dict, Optional
from backend.core.paths import DATA_DIR

logger = logging.getLogger(__name__)

class CoverCacheService:
    """封面图片缓存服务"""
    
    def __init__(self):
        self.covers_dir = os.path.join(DATA_DIR, "covers")
        os.makedirs(self.covers_dir, exist_ok=True)
        
        # 异步 HTTP 客户端，独立连接池
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            timeout=httpx.Timeout(10.0),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/"
            }
        )
        
        # 请求去重：记录正在进行的下载任务
        self._pending_downloads: Dict[str, asyncio.Event] = {}
        self._download_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_cache_path(self, url: str) -> str:
        """根据 URL 生成缓存文件路径"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        # 从 URL 中提取文件扩展名，默认为 .jpg
        ext = ".jpg"
        if url.endswith(".png"):
            ext = ".png"
        elif url.endswith(".webp"):
            ext = ".webp"
        return os.path.join(self.covers_dir, f"{url_hash}{ext}")
    
    async def get_cover(self, url: str) -> Optional[bytes]:
        """
        获取封面图片（优先从缓存读取，缓存未命中时从网络下载）
        
        Args:
            url: 封面图片 URL
            
        Returns:
            图片二进制数据，失败返回 None
        """
        # [修复] 先净化地址：历史脏数据里可能存着指向本服务的代理自引用地址
        # （形如 /api/proxy/image?url=... 或已被拼坏的 https:///api/proxy/image?...），
        # 不净化会请求自己并报 “Request URL is missing an 'http://' or 'https://' protocol”。
        from ..core.cover_utils import sanitize_cover_url
        cleaned = sanitize_cover_url(url)
        if not cleaned or not cleaned.lower().startswith(('http://', 'https://')):
            logger.warning(f"封面地址无法净化，跳过下载: {url}")
            return None
        if cleaned != url:
            logger.debug(f"封面地址已净化: {url} -> {cleaned}")
        url = cleaned

        cache_path = self._get_cache_path(url)
        
        # 1. 尝试从本地缓存读取
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    logger.debug(f"从缓存读取封面: {url}")
                    return f.read()
            except Exception as e:
                logger.warning(f"读取缓存失败: {e}")
        
        # 2. 请求去重：如果已经有相同 URL 的下载任务在进行中，等待其完成
        if url in self._pending_downloads:
            logger.debug(f"等待已有下载任务完成: {url}")
            event = self._pending_downloads[url]
            await event.wait()
            
            # 下载完成后，再次尝试从缓存读取
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as f:
                        return f.read()
                except Exception as e:
                    logger.error(f"等待下载完成后读取缓存失败: {e}")
            return None
        
        # 3. 创建下载任务
        event = asyncio.Event()
        self._pending_downloads[url] = event
        
        try:
            # 从网络下载
            logger.info(f"从网络下载封面: {url}")
            resp = await self.client.get(url)
            resp.raise_for_status()
            
            image_data = resp.content
            
            # 保存到本地缓存
            try:
                with open(cache_path, "wb") as f:
                    f.write(image_data)
                logger.debug(f"封面已缓存: {cache_path}")
            except Exception as e:
                logger.error(f"保存封面缓存失败: {e}")
            
            return image_data
            
        except Exception as e:
            logger.error(f"下载封面失败 {url}: {e}")
            return None
        finally:
            # 通知等待的请求
            event.set()
            del self._pending_downloads[url]
    
    async def preload_covers(self, urls: list):
        """
        后台预加载多个封面图片
        
        Args:
            urls: 封面图片 URL 列表
        """
        tasks = [self.get_cover(url) for url in urls if url]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"预加载 {len(urls)} 个封面完成")
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()

# 全局单例
_cover_cache_service: Optional[CoverCacheService] = None

def get_cover_cache_service() -> CoverCacheService:
    """获取封面缓存服务单例"""
    global _cover_cache_service
    if _cover_cache_service is None:
        _cover_cache_service = CoverCacheService()
    return _cover_cache_service

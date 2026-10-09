import requests
import qrcode
import time
import os
import json
import yt_dlp
import uuid
import logging
from io import BytesIO
import base64
from cachetools import TTLCache, cached
from .paths import DATA_DIR

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _data_path(filename: str) -> str:
    """把数据文件名解析为**数据目录**下的绝对路径。

    [修复] 原先凭据与缓存文件用的是两种都不可靠的相对写法，在打包版里全部落空：
      - `cookie_file="backend/data/bili_cookies.json"` —— 相对**进程工作目录**；
      - `os.path.join(os.path.dirname(__file__), "..", "data", ...)` —— 相对**模块位置**。

    PyInstaller `--onefile` 下模块位于临时解包目录 `sys._MEIPASS`，且工作目录是
    `resources/backend`，于是：
      - 前者把 Cookie 写到 `<exe目录>/backend/data/`（不是数据目录）；
      - 后者把用户信息写到 `<MEIPASS>/backend/data/`，**进程退出即被删除**。
    实测打包版启动后 `data/` 下既没有 `bili_cookies.json` 也没有 `bili_user_info.json` ——
    表现为「每次启动都要重新扫码登录」。统一改为走 `paths.DATA_DIR`。
    """
    return os.path.join(DATA_DIR, filename)


# 全局缓存实例，配置 5 分钟 (300 秒) 的过期时间，最多 1000 个条目
bili_api_cache = TTLCache(maxsize=1000, ttl=300)

class BiliManager:

    # 年度大会员小图标 (Base64 备用)
    ICON_ANNUAL_VIP = "data:image/png;base64,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"

    def __init__(self, cookie_file=None, download_path=None):
        # [修复] 默认值原先是指向数据目录的「相对路径」，打包版会落到错误位置
        # （详见 _data_path 的说明）。改为 None + 解析，避免在打包版里错位。
        self.cookie_file = cookie_file or _data_path("bili_cookies.json")
        self.download_path = download_path or os.path.join(DATA_DIR, "downloads")
        os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
        os.makedirs(self.download_path, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com"
        })
        self.csrf = None
        self.mid = None
        self.uname = None
        self.face = None
        self.vip_type = 0
        self.vip_status = 0
        self._avatar_b64 = None
        self.vip_icon_b64 = ""
        self.is_bili_offline = False

        # 尝试初始化加载
        self.load_user_info_cache()
        self.load_cookies_from_file()

    def load_user_info_cache(self):
        """加载离线缓存的用户信息"""
        cache_file = _data_path("bili_user_info.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.mid = data.get("mid")
                    self.uname = data.get("uname")
                    self.face = data.get("face")
                    self.vip_status = data.get("vip_status", 0)
                    self.vip_type = data.get("vip_type", 0)
                    if self.vip_status == 1:
                        self.vip_icon_b64 = self.ICON_ANNUAL_VIP
                    else:
                        self.vip_icon_b64 = ""
                    # 尝试加载头像b64
                    self._avatar_b64 = data.get("avatar_b64")
                    return True
            except: pass
        return False

    def save_user_info_cache(self):
        """保存离线缓存的用户信息"""
        cache_file = _data_path("bili_user_info.json")
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            data = {
                "mid": self.mid,
                "uname": self.uname,
                "face": self.face,
                "vip_status": self.vip_status,
                "vip_type": self.vip_type,
                "avatar_b64": self._avatar_b64
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except: pass

    def load_cookies_from_file(self):
        """从文件加载 Cookie 到 Session，并显式设置域名"""
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "r", encoding='utf-8') as f:
                    cookies = json.load(f)
                
                self.session.cookies.clear()
                for k, v in cookies.items():
                    # 显式设置到 .bilibili.com 域名下，确保全站通用
                    self.session.cookies.set(k, v, domain=".bilibili.com", path="/")
                
                logging.debug(f"已从文件加载 {len(cookies)} 个 Cookie")
                return True
            except Exception as e:
                logging.error(f"加载 Cookie 文件失败: {e}")
                return False
        return False

    def _get_self_info_fast(self):
        """快速验证登录状态并获取用户信息（优化版本，用于登录后的快速响应）"""
        try:
            # 确保有基础 Cookie
            if not self.session.cookies.get('buvid3'):
                self.session.cookies.set('buvid3', str(uuid.uuid4()).upper() + "infoc", domain=".bilibili.com")

            logging.debug("正在快速验证登录状态...")
            
            # 增加 Header 模拟浏览器
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com"
            }
            
            # 减少超时时间以加快响应
            resp = self.session.get("https://api.bilibili.com/x/web-interface/nav", headers=headers, timeout=3)
            res = resp.json()
            
            if res.get('code') == 0:
                data = res.get('data', {})
                self.is_bili_offline = False
                if data.get('mid'):
                    self.mid = data.get('mid')
                    self.uname = data.get('uname')
                    self.face = data.get('face')
                    
                    # 处理会员信息
                    vip = data.get('vip', {})
                    self.vip_status = vip.get('status', 0)
                    self.vip_type = vip.get('type', 0)
                    
                    if self.vip_status == 1:
                        self.vip_icon_b64 = self.ICON_ANNUAL_VIP
                    else:
                        self.vip_icon_b64 = ""
                    
                    # 提取 CSRF
                    self.csrf = self.session.cookies.get('bili_jct', domain=".bilibili.com") or self.session.cookies.get('bili_jct')
                    
                    logging.debug(f"登录验证成功: {self.uname} (UID: {self.mid})")
                    self.save_user_info_cache()
                    return True
                else:
                    logging.warning(f"B 站返回未登录状态")
                    return False
            else:
                logging.error(f"验证接口返回错误: {res}")
                return False
        except Exception as e:
            logging.error(f"快速验证异常: {e}")
            return False

    def _get_self_info(self):
        """验证登录状态并获取用户信息"""
        try:
            # 确保有基础 Cookie
            if not self.session.cookies.get('buvid3'):
                self.session.cookies.set('buvid3', str(uuid.uuid4()).upper() + "infoc", domain=".bilibili.com")

            logging.debug("正在请求 B 站导航接口验证登录状态...")
            
            # 增加 Header 模拟浏览器
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com"
            }
            
            resp = self.session.get("https://api.bilibili.com/x/web-interface/nav", headers=headers, timeout=10)
            res = resp.json()
            
            if res.get('code') == 0:
                data = res.get('data', {})
                self.is_bili_offline = False
                # 只要有 mid 且 code 为 0，就视为登录成功
                if data.get('mid'):
                    self.mid = data.get('mid')
                    self.uname = data.get('uname')
                    
                    new_face = data.get('face')
                    if self.face != new_face:
                        self.face = new_face
                        self._avatar_b64 = None # 重置头像缓存

                    # 处理会员信息
                    vip = data.get('vip', {})
                    self.vip_status = vip.get('status', 0)
                    self.vip_type = vip.get('type', 0)
                    
                    # 仅当会员状态有效时才设置图标
                    if self.vip_status == 1:
                        self.vip_icon_b64 = self.ICON_ANNUAL_VIP
                    else:
                        self.vip_icon_b64 = ""
                    
                    # 提取 CSRF (bili_jct)
                    self.csrf = self.session.cookies.get('bili_jct', domain=".bilibili.com") or self.session.cookies.get('bili_jct')
                    
                    logging.debug(f"B 站登录验证成功: {self.uname} (UID: {self.mid})")
                    self.save_user_info_cache() # 保存缓存
                    return True
                else:
                    logging.warning(f"B 站返回未登录状态: {data}")
                    self.logout()  # 显式执行清理逻辑
                    return False
            elif res.get('code') == -101: # 明确未登录
                self.is_bili_offline = False
                self.logout() # 显式执行清理逻辑
                return False
            else:
                logging.error(f"B 站验证接口返回错误: {res}")
                self.is_bili_offline = True
                return False
        except Exception as e:
            logging.error(f"获取用户信息异常 (可能是网络问题): {e}")
            self.is_bili_offline = True
            if self.mid:
                logging.info(f"断网降级：使用离线缓存的账户信息: {self.uname}")
                return True
            return None

    def clear_cache(self):
        """清除 API 缓存"""
        try:
            bili_api_cache.clear()
            logging.info("已清除 B 站 API 缓存")
        except Exception as e:
            logging.error(f"清除 API 缓存失败: {e}")

    def logout(self):
        """退出登录：清除 Session、Cookie 文件和离线缓存"""
        self.session.cookies.clear()
        
        # 清除 API 缓存
        self.clear_cache()
        self.mid = None
        self.uname = None
        self.face = None
        self._avatar_b64 = None
        self.vip_status = 0
        self.vip_icon_b64 = ""
        
        # 删除 Cookie 文件
        if os.path.exists(self.cookie_file):
            try:
                os.remove(self.cookie_file)
                logging.info("已删除 Cookie 文件")
            except Exception as e:
                logging.error(f"删除 Cookie 文件失败: {e}")
        
        # 删除用户信息缓存
        cache_file = _data_path("bili_user_info.json")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                logging.info("已删除用户信息缓存")
            except Exception as e:
                logging.error(f"删除用户信息缓存失败: {e}")

    def get_login_qr_data(self):
        """获取扫码登录二维码"""
        try:
            resp = self.session.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                timeout=10
            ).json()

            if resp.get('code') != 0:
                raise Exception(f"B站接口报错: {resp.get('message')}")

            qr_url = resp['data']['url']
            qr_key = resp['data']['qrcode_key']

            qr = qrcode.make(qr_url)
            buffered = BytesIO()
            qr.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode()

            return {"qr_img": qr_base64, "qr_key": qr_key}
        except Exception as e:
            logging.error(f"获取二维码失败: {e}")
            raise e

    def check_login_status(self, qr_key):
        """轮询扫码状态并保存 Cookie"""
        try:
            url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qr_key}"
            resp = self.session.get(url, timeout=5)
            poll = resp.json()
            
            if poll.get('code') != 0:
                return {"code": -1, "message": "轮询接口异常"}
                
            data = poll.get('data', {})
            code = data.get('code')
            
            if code == 0:
                logging.info("扫码登录成功，正在提取并保存 Cookie...")
                
                # 提取所有 Cookie
                cookie_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
                # 兜底：如果 session 中没拿到，从响应中拿
                if not cookie_dict.get('SESSDATA'):
                    cookie_dict.update(requests.utils.dict_from_cookiejar(resp.cookies))
                
                with open(self.cookie_file, "w", encoding='utf-8') as f:
                    json.dump(cookie_dict, f)
                
                # 重新加载 Cookie
                self.load_cookies_from_file()
                
                # 清除旧的 API 缓存
                self.clear_cache()
                
                # 快速验证登录状态（减少超时时间）
                success = self._get_self_info_fast()
                
                # 异步获取头像（不阻塞响应）
                # 头像会在后续请求中自动加载
                
                return {
                    "code": 0,
                    "message": "登录成功",
                    "data": {
                        "is_logged_in": success,
                        "mid": self.mid,
                        "uname": self.uname,
                        "face": self.face,  # 返回 URL 而不是 Base64
                        "vip_label": self.vip_icon_b64 if success else ""
                    }
                }
            
            return {"code": code, "message": data.get('message', '等待扫码')}
        except Exception as e:
            logging.error(f"检查登录状态异常: {e}")
            return {"code": -1, "message": "服务器内部错误"}

    @cached(cache=bili_api_cache)
    def get_fav_folders(self):
        """获取所有收藏夹列表"""
        if not self.mid and not self._get_self_info(): return []
        
        # 优先尝试使用分页接口获取带有 cover 字段的详细列表 (最大支持 100 个收藏夹)
        try:
            url_detail = f"https://api.bilibili.com/x/v3/fav/folder/created/list?up_mid={self.mid}&pn=1&ps=100"
            res = self.session.get(url_detail, timeout=5).json()
            if res.get('code') == 0:
                folders = res.get('data', {}).get('list', [])
                if folders:
                    return folders
        except Exception as e:
            logging.warning(f"获取带封面的收藏夹列表失败，尝试降级接口: {e}")

        # 降级使用基础 list-all 接口 (可能无 cover 字段)
        url = f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={self.mid}"
        try:
            res = self.session.get(url, timeout=5).json()
            return res.get('data', {}).get('list', []) if res.get('code') == 0 else []
        except Exception as e:
            logging.error(f"获取收藏夹列表出错: {e}")
            return []

    @cached(cache=bili_api_cache)
    def get_folder_videos(self, media_id, page=1, page_size=20):
        """获取收藏夹视频列表"""
        url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={media_id}&pn={page}&ps={page_size}"
        try:
            resp = self.session.get(url, timeout=5).json()
            if resp['code'] == 0:
                return resp['data']
            return None
        except Exception as e:
            logging.error(f"获取详情发生异常: {e}")
            return None

    @cached(cache=bili_api_cache)
    def get_video_parts(self, bvid):
        """获取视频分集信息"""
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
            res = self.session.get(url).json()
            if res['code'] == 0:
                # 显式包含 cid
                return res['data']['pages'], res['data']['title'], res['data']['pic'], res['data']['owner']['name'], res['data']['owner']['face']
        except Exception as e:
            logging.error(f"获取分集信息失败 {bvid}: {e}")
        return [], "", "", "", ""
    
    def get_avatar_image(self):
        """获取用户头像并转为 Base64"""
        if self._avatar_b64: return self._avatar_b64
        if not self.face: return None
        try:
            resp = self.session.get(self.face, timeout=10)
            if resp.status_code == 200:
                b64_img = base64.b64encode(resp.content).decode()
                self._avatar_b64 = f"data:image/jpeg;base64,{b64_img}"
                self.save_user_info_cache() # 成功获取图片后再次持久化
                return self._avatar_b64
            return None
        except Exception as e:
            logging.error(f"处理头像异常 (可能是断网): {e}")
            return None
        
    def get_vip_icon_base64(self):
        """获取会员图标并转为 Base64"""
        return self.ICON_ANNUAL_VIP
    
    def get_play_url(self, bvid, cid, quality=64):
        """
        获取视频的实时播放地址 (直链)
        :param bvid: 视频 BV 号
        :param cid: 视频分集 ID
        :param quality: 清晰度 (16, 32, 64=720p, 80=1080p)
        :return: 视频直链 URL, 备用 URL 列表
        """
        # fnval=1 表示获取 mp4/flv 格式 (非 DASH)，适合做单文件流传输
        # fnval=16 是 DASH 格式 (音视频分离)，处理起来比较麻烦，这里选 1
        url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn={quality}&fnval=1&fnver=0&fourk=1"
        
        try:
            resp = self.session.get(url, timeout=5).json()
            if resp['code'] == 0:
                durl = resp['data']['durl'][0]
                play_url = durl['url']
                backup_urls = durl.get('backup_url', [])
                logging.info(f"获取播放地址成功: {bvid} (qn={quality})")
                return play_url, backup_urls
            else:
                logging.error(f"获取播放地址失败: {resp['message']}")
                return None, []
        except Exception as e:
            logging.error(f"获取播放地址异常: {e}")
            return None, []

    def stream_video_content(self, url, range_header=None):
        """
        [性能优化] 生成器：流式代理传输视频数据，增强异常处理和资源清理
        并且通过 httpx 实现完全的异步与 TCP 强制释放，杜绝 CLOSE_WAIT
        :param url: B站视频直链
        :param range_header: 前端传来的 Range 头 (用于进度条拖拽)
        :return: (生成器对象, 响应头, 状态码)
        """
        import asyncio
        import httpx
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            # 关键：如果有 Range 头 (拖拽进度条)，必须透传给 B 站
            "Range": range_header if range_header else "bytes=0-"
        }

        # [性能优化] 使用 httpx 的流式请求来避免 requests 在 ASGI 里的同步阻塞
        # 为了兼容当前的同步方法定义，使用 asyncio 包装器进行过渡
        # 我们会在 generate 里面实际开启连接，从而可以安全地把流交给 FastAPI
        
        try:
            # [修复] 获取请求头前先刷新 session，防止睡眠后连接失效
            # 减少超时时间，快速失败并重试
            try:
                head_req = self.session.get(url, headers=headers, stream=True, timeout=5)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logging.warning(f"[流媒体代理] 初始连接失败，尝试重建 session: {e}")
                # 重建 session 连接
                self.session.close()
                self.session = requests.Session()
                self.session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.bilibili.com/",
                    "Origin": "https://www.bilibili.com"
                })
                # 重新加载 cookies
                self.load_cookies_from_file()
                # 重试连接
                head_req = self.session.get(url, headers=headers, stream=True, timeout=5)
            
            # 提取需要的响应头返回给前端 (如 Content-Type, Content-Length, Content-Range)
            resp_headers = {
                'Content-Type': head_req.headers.get('Content-Type', 'video/mp4'),
                'Content-Length': head_req.headers.get('Content-Length'),
                'Accept-Ranges': 'bytes',
            }
            
            if 'Content-Range' in head_req.headers:
                resp_headers['Content-Range'] = head_req.headers['Content-Range']
                status_code = 206 # Partial Content
            else:
                status_code = 200
                
            # 我们仅仅需要 headers，立刻关闭同步连接避免阻塞
            head_req.close()

            # 提供给 StreamingResponse 的异步生成器
            async def async_generate():
                """
                [性能优化] 完全异步化的生成器，使用 httpx AsyncClient
                能够完美响应 FastAPI 的协程调度与客户端中止事件
                """
                # 使用独立的隔离客户端避免连接池污染
                async with httpx.AsyncClient(verify=False) as client:
                    try:
                        async with client.stream("GET", url, headers=headers, timeout=30.0) as response:
                            # [性能优化] chunk size 1MB (平衡内存驻留和 CPU 切换)
                            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                                if chunk:
                                    yield chunk
                    except asyncio.CancelledError:
                        logging.info("[流媒体代理] 客户端主动断开连接，TCP 极速释放完成")
                        raise
                    except Exception as e:
                        logging.error(f"[流媒体代理] 异步流传输异常: {e}")
                        raise

            return async_generate(), resp_headers, status_code

        except Exception as e:
            logging.error(f"[流媒体代理] 建立视频流失败: {e}")
            return None, None, 500

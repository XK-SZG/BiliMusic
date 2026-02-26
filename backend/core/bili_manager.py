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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BiliManager:

    # 年度大会员小图标 (Base64 备用)
    ICON_ANNUAL_VIP = "data:image/png;base64,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"

    def __init__(self, cookie_file="backend/data/bili_cookies.json", download_path="backend/data/downloads"):
        self.cookie_file = cookie_file
        self.download_path = download_path
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
        cache_file = os.path.join(os.path.dirname(__file__), "..", "data", "bili_user_info.json")
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
        cache_file = os.path.join(os.path.dirname(__file__), "..", "data", "bili_user_info.json")
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
                
                logging.info(f"已从文件加载 {len(cookies)} 个 Cookie")
                return True
            except Exception as e:
                logging.error(f"加载 Cookie 文件失败: {e}")
                return False
        return False

    def _get_self_info(self):
        """验证登录状态并获取用户信息"""
        try:
            # 确保有基础 Cookie
            if not self.session.cookies.get('buvid3'):
                self.session.cookies.set('buvid3', str(uuid.uuid4()).upper() + "infoc", domain=".bilibili.com")

            logging.info("正在请求 B 站导航接口验证登录状态...")
            
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
                    
                    logging.info(f"B 站登录验证成功: {self.uname} (UID: {self.mid})")
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

    def logout(self):
        """退出登录：清除 Session、Cookie 文件和离线缓存"""
        self.session.cookies.clear()
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
        cache_file = os.path.join(os.path.dirname(__file__), "..", "data", "bili_user_info.json")
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
            resp = self.session.get(url, timeout=10)
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
                
                # 重新加载并验证
                self.load_cookies_from_file()
                success = self._get_self_info()
                
                return {
                    "code": 0,
                    "message": "登录成功",
                    "data": {
                        "is_logged_in": success,
                        "mid": self.mid,
                        "uname": self.uname,
                        "face": self.get_avatar_image() if success else None,
                        "vip_label": self.vip_icon_b64 if success else ""
                    }
                }
            
            return {"code": code, "message": data.get('message', '等待扫码')}
        except Exception as e:
            logging.error(f"检查登录状态异常: {e}")
            return {"code": -1, "message": "服务器内部错误"}

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

    def get_video_parts(self, bvid):
        """获取视频分集信息"""
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
            res = self.session.get(url).json()
            if res['code'] == 0:
                # 显式包含 cid
                return res['data']['pages'], res['data']['title'], res['data']['pic'], res['data']['owner']['name']
        except Exception as e:
            logging.error(f"获取分集信息失败 {bvid}: {e}")
        return [], "", "", ""
    
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
        生成器：流式代理传输视频数据
        :param url: B站视频直链
        :param range_header: 前端传来的 Range 头 (用于进度条拖拽)
        :return: (生成器对象, 响应头)
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            # 关键：如果有 Range 头 (拖拽进度条)，必须透传给 B 站
            "Range": range_header if range_header else "bytes=0-"
        }

        try:
            # stream=True 是关键，表示不一次性下载，而是建立管道
            req = self.session.get(url, headers=headers, stream=True, timeout=20)
            
            # 提取需要的响应头返回给前端 (如 Content-Type, Content-Length, Content-Range)
            resp_headers = {
                'Content-Type': req.headers.get('Content-Type', 'video/mp4'),
                'Content-Length': req.headers.get('Content-Length'),
                'Accept-Ranges': 'bytes',
            }
            
            if 'Content-Range' in req.headers:
                resp_headers['Content-Range'] = req.headers['Content-Range']
                status_code = 206 # Partial Content
            else:
                status_code = 200

            def generate():
                try:
                    # 每次读取 4KB 数据块
                    for chunk in req.iter_content(chunk_size=1024 * 4):
                        if chunk:
                            yield chunk
                except Exception as e:
                    logging.error(f"流传输中断: {e}")
                finally:
                    req.close()

            return generate(), resp_headers, status_code

        except Exception as e:
            logging.error(f"建立视频流失败: {e}")
            return None, None, 500

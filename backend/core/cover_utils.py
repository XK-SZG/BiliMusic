# -*- coding: utf-8 -*-
# Path: backend/core/cover_utils.py
"""封面地址净化工具。

背景（v1.0.22 修复的真实缺陷）：
    前端的 ``formatImg()`` 产出的是「浏览器可直接加载的展示地址」，在开发环境下是
    同源相对路径 ``/api/proxy/image?url=<原始直链>``。但历史上有两处调用点误把它的
    结果写回了数据库（导入 B 站视频到本地媒体库时），于是 ``videos.pic`` 里存下了
    **指向自己的代理地址**：

        pic = "/api/proxy/image?url=https%3A%2F%2Fi0.hdslb.com%2F...%40640w_360h_1c_1s.webp"

    再次展示时，前端把该相对路径当作「协议相对 URL」拼成 ``https:///api/proxy/image?...``
    （三斜杠、无主机名），后端 ``cover_cache_service`` 收到后报
    ``Request URL is missing an 'http://' or 'https://' protocol``，
    最终表现为：收藏夹卡片封面、本地媒体卡片封面在某几个页面全部加载失败。

    本模块提供 ``sanitize_cover_url()``：把任意层级的代理包装逐层剥掉，
    还原成真正的图片直链，供后端在下载封面 / 返回数据前做一次兜底净化。

设计约束：
    - 纯标准库，可被任意模块安全导入；
    - 绝不抛异常，任何异常都退化为「返回原值或空串」；
    - 幂等：对已经干净的地址调用不会产生任何改变。
"""

import re
from urllib.parse import parse_qs, unquote, urlparse

#: 最多剥离的代理层数（防御畸形/自引用数据造成的死循环）
MAX_UNWRAP_DEPTH = 5

#: 形如 `.../proxy/image?url=...` 的代理地址特征
_PROXY_PATH_RE = re.compile(r'/proxy/image\b', re.IGNORECASE)

#: 匹配 `url=` 查询参数的值（值可能未被编码，含 `:` `/` `?` `&` 等）
_URL_PARAM_RE = re.compile(r'[?&]url=([^&]+)', re.IGNORECASE)

#: 合法的绝对 http(s) 地址
_ABSOLUTE_RE = re.compile(r'^https?://[^/\s]+', re.IGNORECASE)


def _extract_proxy_target(value: str):
    """若 value 是代理地址，返回其内部的目标地址；否则返回 None。"""
    if not _PROXY_PATH_RE.search(value):
        return None

    # 优先用 urlparse + parse_qs（能正确处理已编码的值）
    try:
        query = urlparse(value).query
        if query:
            params = parse_qs(query)
            for key in ('url', 'target', 'src'):
                if params.get(key):
                    return params[key][0]
    except Exception:
        pass

    # 回退：直接从字符串里抓 `url=` 之后的内容（应对缺协议前缀的畸形地址）
    match = _URL_PARAM_RE.search(value)
    if match:
        return match.group(1)
    return None


def sanitize_cover_url(url, max_depth: int = MAX_UNWRAP_DEPTH) -> str:
    """把封面地址净化成可直接请求的形态。

    处理内容：
    1. 逐层剥离 ``/api/proxy/image?url=...`` 代理包装（含嵌套多层的历史脏数据）；
    2. 解 URL 编码；
    3. 丢弃因脏数据产生的畸形地址（形如 ``https:///api/...``，即三斜杠无主机名）；
    4. 其余情况原样返回（本地文件名、``/local_covers/xxx``、正常的 http(s) 直链）。

    :return: 净化后的地址；无法还原时返回空串（调用方据此跳过下载）
    """
    if not url:
        return ''
    try:
        value = str(url).strip()
    except Exception:
        return ''

    if not value:
        return ''

    # 1) 逐层剥代理
    unwrapped_any = False
    for _ in range(max(1, max_depth)):
        target = _extract_proxy_target(value)
        if not target:
            break
        try:
            target = unquote(target)
        except Exception:
            pass
        target = target.strip()
        if not target or target == value:
            break
        value = target
        unwrapped_any = True

    # 2) 畸形地址检测：`http://` 或 `https://` 之后紧跟 `/`（三斜杠 = 主机名为空）
    if re.match(r'^https?:///', value, re.IGNORECASE):
        return ''

    # 3) 仍指向前端代理接口且无法还原出目标 → 丢弃，避免自请求打转
    if _PROXY_PATH_RE.search(value) and not _ABSOLUTE_RE.match(value):
        if not unwrapped_any:
            return ''
        # 已成功剥离过至少一层，但结果又指回代理 → 视为畸形
        if value.startswith('/'):
            return ''

    return value


def is_remote_http_url(url) -> bool:
    """判断净化后的地址是否为可请求的远程 http(s) 直链。"""
    cleaned = sanitize_cover_url(url)
    return bool(cleaned) and bool(_ABSOLUTE_RE.match(cleaned))


def normalize_pic_for_storage(pic):
    """写库前的封面地址归一化。

    只保留可长期使用的形态：
    - 远程 http(s) 直链 → 原样保留；
    - 同源相对路径（``/local_covers/xxx``）→ 原样保留；
    - 代理自引用地址 / 畸形地址 → 还原或丢弃。
    """
    cleaned = sanitize_cover_url(pic)
    if not cleaned:
        return ''
    if _ABSOLUTE_RE.match(cleaned):
        return cleaned
    if cleaned.startswith('/') and not cleaned.startswith('//'):
        return cleaned
    # 既不是绝对地址也不是同源路径（例如裸文件名）：交由调用方按原语义处理
    return cleaned

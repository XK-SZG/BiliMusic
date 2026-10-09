# -*- coding: utf-8 -*-
# Path: backend/core/utils.py
"""跨模块共用的小工具。

本模块只依赖标准库，可被任意模块安全导入（包括 log_manager / config 等基础设施）。
"""


def as_bool(value, default=False):
    """把配置值稳健地转成布尔。

    [修复] 直接 ``bool(...)`` 会踩字符串陷阱：YAML 里写 ``console: "false"``
    或 ``keep_failed_files: "0"`` 时，``bool("false")`` 与 ``bool("0")`` 都是 True，
    用户以为关掉了某项行为，实际仍然开着。

    :param value: 待转换的值（None / bool / 数字 / 字符串）
    :param default: 无法识别时返回的默认值
    :return: 转换后的布尔值
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ('false', '0', 'no', 'off', 'none', 'null', ''):
        return False
    if text in ('true', '1', 'yes', 'on'):
        return True
    return default

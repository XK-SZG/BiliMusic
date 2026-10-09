# -*- coding: utf-8 -*-
# Path: backend/core/config.py

import os
import sys
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

#: 配置文件名的固定写法（打包时会作为数据文件放在 exe 同级或 _MEIPASS 内）
CONFIG_FILENAME = 'config.yaml'


def resolve_config_path(explicit: Optional[str] = None) -> str:
    """确定配置文件的实际路径。

    历史缺陷：``run_backend.py`` 会设置 ``BILIMUSIC_CONFIG_PATH`` 环境变量，
    但本模块从未读取它，且默认值只是相对路径 ``"config.yaml"``（相对于进程工作目录）。
    打包后进程工作目录是 ``resources/backend``，且该环境变量形同虚设，于是
    **打包版永远读不到 config.yaml，全程使用内置默认值**——用户改端口、改缓存上限、
    改日志保留策略在安装版上全部无效（开发环境因为工作目录是仓库根目录才「看起来正常」）。

    查找顺序（命中即返回）：
    1. 显式传入的参数（调用方指定，优先级最高）；
    2. 环境变量 ``BILIMUSIC_CONFIG_PATH``（由 ``run_backend.py`` 探测后写入）；
    3. 冻结环境下 exe 所在目录（用户可直接编辑，最符合「就地改配置」的预期）；
    4. 冻结环境下 PyInstaller 解包目录 ``sys._MEIPASS``（随包发布的默认配置）；
    5. 源码仓库根目录（开发环境）；
    6. 进程当前工作目录（兜底）。

    :return: 命中的路径；全部不存在时返回兜底的相对路径 ``"config.yaml"``
    """
    candidates = []

    if explicit:
        candidates.append(explicit)

    env_path = os.environ.get('BILIMUSIC_CONFIG_PATH')
    if env_path:
        candidates.append(env_path)

    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), CONFIG_FILENAME))
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(os.path.join(meipass, CONFIG_FILENAME))

    # backend/core/config.py -> 上溯三级即仓库根目录
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    candidates.append(os.path.join(repo_root, CONFIG_FILENAME))

    candidates.append(os.path.join(os.getcwd(), CONFIG_FILENAME))

    for path in candidates:
        if path and os.path.exists(path):
            return path

    return CONFIG_FILENAME


class Config:
    """配置管理类，从 config.yaml 加载配置"""

    def __init__(self, config_path: Optional[str] = None):
        # 传入 None 时按 resolve_config_path() 的顺序自动查找；
        # 显式路径不存在时同样回退到自动查找，最后才落到默认值
        # （而不是像旧实现那样直接丢掉仓库里的 config.yaml）。
        self.config_path = resolve_config_path(config_path)
        self._config: Dict[str, Any] = {}
        self.load()

    @classmethod
    def from_defaults(cls) -> "Config":
        """构造一个只使用内置默认值的配置实例（不读磁盘）。

        供「确认默认值与 config.yaml.example 一致」这类自检使用，
        避免因磁盘上恰好存在 config.yaml 而测不到默认值分支。
        """
        instance = cls.__new__(cls)
        instance.config_path = ''
        instance._config = instance._get_default_config()
        return instance

    def load(self):
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
            self._config = self._get_default_config()
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"成功加载配置文件: {self.config_path}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置。

        [修复] 原实现缺少 ``logging`` 整段与 ``download.keep_failed_files``，
        而 ``log_manager``（内存条数、单文件体积、文件数量、总占用）与
        ``download_service`` 都直接按这些键读取配置。默认值缺项会触发两条不一致：
          1. 与 ``config.yaml.example`` 对不上，``docs/配置说明.md`` 里承诺可调的
             日志保留策略实际上只能拿到硬编码兜底值；
          2. 非法/损坏的 config.yaml 回退到默认值后，日志与下载行为会静默改变。
        此处与 ``config.yaml.example`` 保持一一对应。
        """
        return {
            'server': {
                'host': '127.0.0.1',
                'port': 12180,
                'debug': False
            },
            'storage': {
                'download_path': 'backend/data/downloads',
                'cache_limit_gb': 10
            },
            'scheduler': {
                'cleanup_interval_hours': 6
            },
            'download': {
                'max_workers': 3,
                'max_retries': 3,
                'keep_failed_files': True
            },
            'logging': {
                'level': 'DEBUG',
                'console': True,
                'file_enabled': True,
                'memory_capacity': 20000,
                'max_file_mb': 5,
                'max_files': 5,
                'max_total_mb': 25
            },
            'database': {
                'pool_size': 20,
                'max_overflow': 40,
                'pool_timeout': 10,
                'pool_recycle': 1800
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的嵌套键"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_server_config(self) -> Dict[str, Any]:
        """获取服务器配置"""
        return self.get('server', {})
    
    def get_storage_config(self) -> Dict[str, Any]:
        """获取存储配置"""
        return self.get('storage', {})
    
    def get_download_config(self) -> Dict[str, Any]:
        """获取下载配置"""
        return self.get('download', {})
    
    def get_database_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.get('database', {})
    
    def get_scheduler_config(self) -> Dict[str, Any]:
        """获取调度器配置"""
        return self.get('scheduler', {})


# 全局配置实例
_config_instance = None

def get_config() -> Config:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance

# -*- coding: utf-8 -*-
# Path: backend/core/config.py

import os
import yaml
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Config:
    """配置管理类，从 config.yaml 加载配置"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self.load()
    
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
        """获取默认配置"""
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
                'max_retries': 3
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

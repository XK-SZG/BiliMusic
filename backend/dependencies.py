from .core.bili_manager import BiliManager
from .services import download_service, cleanup_service
from .services.playback_service import PlaybackManager

# 全局单例初始化
bili = BiliManager()
downloader = download_service.Downloader(
    download_path=cleanup_service.DOWNLOAD_PATH,
    session=bili.session
)
playback = PlaybackManager()

def get_bili():
    return bili

def get_downloader():
    return downloader

def get_playback():
    return playback

from fastapi import APIRouter, HTTPException, Depends
from ..core.bili_manager import BiliManager
from ..dependencies import get_bili

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/status")
def get_auth_status(bili: BiliManager = Depends(get_bili)):
    """检查登录状态"""
    is_login = bili._get_self_info() 
    is_bili_offline = getattr(bili, 'is_bili_offline', False)
    
    if is_login is None:
        # 无法连接B站且无本地缓存
        return {"is_logged_in": False, "is_bili_offline": is_bili_offline}
        
    if is_login:
        return {
            "is_logged_in": True,
            "is_bili_offline": is_bili_offline,
            "uname": bili.uname,
            "mid": bili.mid,
            "face": bili.get_avatar_image(),
            "vip_label": bili.vip_icon_b64,
            "vip_status": bili.vip_status
        }
    return {"is_logged_in": False, "is_bili_offline": is_bili_offline}

@router.get("/qr")
def get_qr(bili: BiliManager = Depends(get_bili)):
    """获取扫码登录二维码"""
    return bili.get_login_qr_data()

@router.post("/logout")
def logout(bili: BiliManager = Depends(get_bili)):
    """退出登录"""
    bili.logout()
    return {"status": "success"}

@router.get("/check/{qr_key}")
def check_login(qr_key: str, bili: BiliManager = Depends(get_bili)):
    """检查扫码结果"""
    return bili.check_login_status(qr_key)

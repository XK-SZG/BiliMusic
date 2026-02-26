!macro preInit
    SetRegView 64
    WriteRegExpandStr HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\BiliMusic"
    WriteRegExpandStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\BiliMusic"
    SetOutPath $INSTDIR
!macroend

!macro customInit
    MessageBox MB_OK|MB_ICONINFORMATION "提示：BiliMusic 会在安装目录下缓存大量的音视频资源。为了避免占用系统盘空间，建议您将软件安装在非 C 盘（默认已为您选择 D:\BiliMusic）。"
!macroend

!macro customUnInit
    ; 强制结束主程序和后端进程，确保文件没有被锁定
    ExecWait 'taskkill /F /IM BiliMusic.exe /T'
    ExecWait 'taskkill /F /IM backend.exe /T'
    ; 给系统一点时间释放句柄
    Sleep 1000
!macroend

!macro customUnInstall
    MessageBox MB_YESNO|MB_ICONQUESTION "是否要删除 BiliMusic 的所有缓存数据和配置文件？" IDNO skip_delete
    
    ; 再次尝试强制结束进程（双重保险）
    ExecWait 'taskkill /F /IM BiliMusic.exe /T'
    ExecWait 'taskkill /F /IM backend.exe /T'
    Sleep 500

    ; 删除 AppData 中的配置和日志
    RMDir /r "$APPDATA\BiliMusic"
    RMDir /r "$LOCALAPPDATA\BiliMusic"
    
    ; 删除安装目录下的所有文件（包括缓存的音视频资源）
    RMDir /r "$INSTDIR"
    
    skip_delete:
!macroend

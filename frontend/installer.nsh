!include "${BUILD_RESOURCES_DIR}\uninstall_list.nsh"

!macro preInit
    SetRegView 64
    WriteRegExpandStr HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\BiliMusic"
    WriteRegExpandStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\BiliMusic"
    SetOutPath $INSTDIR
!macroend

!macro customInit
    ; 强制结束进程，确保文件没有被锁定
    ExecWait 'taskkill /F /IM BiliMusic.exe /T'
    ExecWait 'taskkill /F /IM backend.exe /T'
    Sleep 1000

    ${If} ${isUpdated}
        ; 检查旧版本是否支持安全卸载（保留数据）
        StrCpy $1 "0"
        ClearErrors
        ReadRegStr $0 HKLM "${UNINSTALL_REGISTRY_KEY}" "KeepDataSupported"
        ${If} $0 == "1"
            StrCpy $1 "1"
        ${EndIf}
        ClearErrors
        ReadRegStr $0 HKCU "${UNINSTALL_REGISTRY_KEY}" "KeepDataSupported"
        ${If} $0 == "1"
            StrCpy $1 "1"
        ${EndIf}

        ${If} $1 == "0"
            ; 旧版本不支持保留数据（如 v1.0.18 及以前）
            ; 1. 阻止旧版卸载程序运行（因为它会删掉所有数据）
            DeleteRegValue HKLM "${UNINSTALL_REGISTRY_KEY}" "UninstallString"
            DeleteRegValue HKCU "${UNINSTALL_REGISTRY_KEY}" "UninstallString"
            !ifdef UNINSTALL_REGISTRY_KEY_2
                DeleteRegValue HKLM "${UNINSTALL_REGISTRY_KEY_2}" "UninstallString"
                DeleteRegValue HKCU "${UNINSTALL_REGISTRY_KEY_2}" "UninstallString"
            !endif
            
            ; 2. 手动清理旧版程序文件（基于当前版本的文件列表，尽力清理）
            !insertmacro cleanOldFiles
        ${EndIf}
        ; 如果 $1 == "1"，说明旧版是安全的，我们什么都不做，让 electron-builder 正常调用旧版卸载程序即可。
    ${EndIf}

    MessageBox MB_OK|MB_ICONINFORMATION "提示：BiliMusic 会在安装目录下缓存大量的音视频资源。为了避免占用系统盘空间，建议您将软件安装在非 C 盘（默认已为您选择 D:\BiliMusic）。"
!macroend

!macro customInstall
    ; 写入标记，表明当前版本支持安全卸载
    WriteRegStr HKLM "${UNINSTALL_REGISTRY_KEY}" "KeepDataSupported" "1"
    WriteRegStr HKCU "${UNINSTALL_REGISTRY_KEY}" "KeepDataSupported" "1"
!macroend

!macro customUnInit
    ; 强制结束主程序和后端进程，确保文件没有被锁定
    ExecWait 'taskkill /F /IM BiliMusic.exe /T'
    ExecWait 'taskkill /F /IM backend.exe /T'
    ; 给系统一点时间释放句柄
    Sleep 1000
!macroend

!macro customUnInstall
    StrCpy $R9 "1"

    ${If} ${isUpdated}
        Goto skip_prompt
    ${EndIf}
    
    ${If} ${Silent}
        Goto skip_prompt
    ${EndIf}

    MessageBox MB_YESNO|MB_ICONQUESTION "是否要删除 BiliMusic 的所有缓存数据和配置文件？" IDNO skip_prompt
    StrCpy $R9 "0"
    
    skip_prompt:
    ; 再次尝试强制结束进程（双重保险）
    ExecWait 'taskkill /F /IM BiliMusic.exe /T'
    ExecWait 'taskkill /F /IM backend.exe /T'
    Sleep 500

    ${If} $R9 == "0"
        ; 删除 AppData 中的配置和日志
        RMDir /r "$APPDATA\BiliMusic"
        RMDir /r "$LOCALAPPDATA\BiliMusic"
    ${EndIf}
!macroend

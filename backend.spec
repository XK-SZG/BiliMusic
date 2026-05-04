# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_backend.py'],
    pathex=[],
    binaries=[],
    datas=[('backend/data', 'data'), ('config.yaml', '.')],
    hiddenimports=['uvicorn', 'fastapi', 'starlette', 'pydantic', 'sqlalchemy', 'sqlite3', 'mutagen', 'pyperclip', 'backend.core.log_manager'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'tkinter', 'PyQt5', 'PySide6', 'IPython', 'jupyter', 'scipy', 'pandas'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

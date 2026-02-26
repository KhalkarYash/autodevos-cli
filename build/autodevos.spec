# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for AutoDevOS CLI.

Build with:
    pyinstaller build/autodevos.spec
"""

import sys
from pathlib import Path

block_cipher = None

# Get the project root
project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / 'autodevos' / 'cli' / 'main.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # Include any data files needed
        (str(project_root / 'prompts'), 'prompts'),
    ],
    hiddenimports=[
        'tiktoken_ext.openai_public',
        'tiktoken_ext',
        'click',
        'rich',
        'httpx',
        'openai',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
        'keyring.backends.Windows',
        'keyring.backends.SecretService',
        'platformdirs',
        'tomlkit',
        'pydantic',
        'pydantic_settings',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ados',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here: 'assets/icon.ico' for Windows
)

# For macOS .app bundle (optional)
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='AutoDevOS.app',
        icon=None,  # Add icon path here: 'assets/icon.icns'
        bundle_identifier='com.autodevos.cli',
        info_plist={
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '0.1.0',
            'NSHighResolutionCapable': True,
        },
    )

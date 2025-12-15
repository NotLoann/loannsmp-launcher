# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # Mise à jour des hiddenimports: Remplacement de PyQt6 par PySide6 et 
    # confirmation des autres dépendances (minecraft_launcher_lib, requests, packaging).
    hiddenimports=[
        # Imports pour PySide6 (GUI)
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        
        # Autres dépendances spécifiques utilisées dans launcher.py
        'minecraft_launcher_lib',
        'requests',
        'packaging',
        'packaging.version',
        'packaging.specifiers',
        'packaging.requirements',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'IPython',
        'notebook',
        'jedi',
        'sphinx',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Supprime les DLLs inutiles pour réduire la taille (conserve l'optimisation) [cite: 7]
a.binaries = [x for x in a.binaries if not x[0].startswith('api-ms-win-')]
a.binaries = [x for x in a.binaries if not x[0].startswith('ucrtbase')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LoannSMP_Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # Conserve l'application en mode fenêtre [cite: 8]
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico', # Conserve l'icône [cite: 8]
    version_info=None,
)

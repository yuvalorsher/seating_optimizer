# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

a = Analysis(
    ['gui/main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('data/office_map.csv', 'data'),
        ('data/teams.json', 'data'),
    ],
    hiddenimports=[
        'seating_optimizer',
        'seating_optimizer.models',
        'seating_optimizer.loader',
        'seating_optimizer.solver',
        'seating_optimizer.scorer',
        'seating_optimizer.constraints',
        'seating_optimizer.updater',
        'seating_optimizer.persistence',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['streamlit', 'pandas', 'altair', 'tornado', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SeatingOptimizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SeatingOptimizer',
)

app = BUNDLE(
    coll,
    name='SeatingOptimizer.app',
    icon=None,
    bundle_identifier='com.seatingoptimizer.app',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'LSMinimumSystemVersion': '12.0',
        'CFBundleName': 'Seating Optimizer',
        'CFBundleDisplayName': 'Seating Optimizer',
    },
)

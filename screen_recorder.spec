# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# 收集 imageio 的所有数据（包括元数据）
imageio_datas, imageio_binaries, imageio_hiddenimports = collect_all('imageio')
imageio_ffmpeg_datas = collect_data_files('imageio_ffmpeg')

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=imageio_binaries,
    datas=[('icon.ico', '.'), ('icon.svg', '.'), ('SHOU.png', '.')] + imageio_datas + imageio_ffmpeg_datas,
    hiddenimports=['cv2', 'numpy', 'mss', 'imageio', 'PIL', 'sounddevice', 'soundfile', 'pyaudiowpatch'] + imageio_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PySide6', 'PySide2',
        'tkinter', 'matplotlib', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook', 'pytest',
        'sphinx', 'docutils', 'babel', 'jedi', 'parso',
        'torch', 'tensorflow', 'keras', 'transformers',
        'spacy', 'thinc', 'datasets', 'huggingface_hub',
        'numba', 'llvmlite', 'pyarrow', 'h5py',
        'bitsandbytes', 'accelerate', 'diffusers',
        'black', 'yapf', 'isort', 'flake8', 'pylint',
        'zmq', 'tornado', 'bokeh', 'plotly', 'seaborn',
        'sklearn', 'scikit-learn', 'xgboost', 'lightgbm',
        'dask', 'distributed', 'ray',
    ],
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
    name='屏幕录制工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

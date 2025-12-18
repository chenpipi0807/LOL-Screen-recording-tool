# 屏幕录制工具

一款简洁易用的屏幕录制工具，支持导出视频和GIF。

## 功能特点

- 🎬 全屏录制
- ⚙️ 可调节帧率 (15/24/30/60 FPS)
- 📊 多种质量选项
- 📹 支持导出 MP4、AVI、WebM 视频格式
- 🎞️ 支持导出 GIF 动图
- 🎨 美观的深色主题界面
- 🇨🇳 中文界面

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行程序

```bash
python main.py
```

## 打包为 EXE

### 方法一：使用批处理文件
双击运行 `build.bat`

### 方法二：手动打包
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "屏幕录制工具" main.py
```

打包完成后，exe文件位于 `dist` 目录下。

## 使用说明

1. **录制选项卡**
   - 选择帧率和质量
   - 点击"开始录制"按钮
   - 点击"停止录制"结束

2. **导出选项卡**
   - 选择导出格式（MP4/AVI/WebM/GIF）
   - 如果导出GIF，可调节GIF帧率
   - 选择输出目录
   - 点击"导出文件"

## 系统要求

- Windows 10/11
- Python 3.8+

## 依赖库

- PyQt5 - GUI界面
- OpenCV - 视频处理
- mss - 屏幕截图
- imageio - GIF导出
- Pillow - 图像处理

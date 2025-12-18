import sys
import os
import time
from datetime import datetime
from pathlib import Path

def resource_path(relative_path):
    """获取资源文件的绝对路径，支持 PyInstaller 打包"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

import cv2
import numpy as np
import mss
import imageio
import tempfile
import subprocess

# 音频录制（可选）
try:
    import sounddevice as sd
    import soundfile as sf
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

# Windows 系统音频录制（WASAPI loopback）- 使用 pyaudiowpatch
SYSTEM_AUDIO_AVAILABLE = False
try:
    import pyaudiowpatch as pyaudio
    SYSTEM_AUDIO_AVAILABLE = True
except ImportError:
    pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSpinBox, QFileDialog,
    QGroupBox, QProgressBar, QMessageBox, QTabWidget,
    QDialog, QRubberBand, QRadioButton, QButtonGroup, QFrame, QCheckBox,
    QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QRect, QPoint
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QRegion, QPainterPath, QPixmap, QIcon

# ==========================================
# 悬浮控制面板 (录制中显示)
# ==========================================
class FloatingControlPanel(QWidget):
    stop_clicked = pyqtSignal()
    reselect_clicked = pyqtSignal()
    hide_main_clicked = pyqtSignal()
    show_main_clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 110) # 稍微加宽
        
        self.drag_pos = None
        self.main_hidden = False
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                border-radius: 10px;
                border: 1px solid #444;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(15, 10, 15, 10)
        
        # 上部分：时间与状态
        top_layout = QHBoxLayout()
        
        self.rec_dot = QLabel("●")
        self.rec_dot.setStyleSheet("color: #ff5555; font-size: 16px;")
        top_layout.addWidget(self.rec_dot)
        
        self.time_label = QLabel("00:00:00")
        self.time_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.time_label.setStyleSheet("color: #ffffff;")
        top_layout.addWidget(self.time_label)
        
        top_layout.addStretch()
        
        self.frame_label = QLabel("0 帧")
        self.frame_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        top_layout.addWidget(self.frame_label)
        
        container_layout.addLayout(top_layout)
        
        # 下部分：按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 样式通用定义
        btn_style = """
            QPushButton {
                background-color: #313244;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
                font-family: "Microsoft YaHei";
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """
        
        stop_style = """
            QPushButton {
                background-color: #ff5555;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 15px;
                font-family: "Microsoft YaHei";
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ff6e6e;
            }
        """

        self.reselect_btn = QPushButton("重选区域")
        self.reselect_btn.setStyleSheet(btn_style)
        self.reselect_btn.clicked.connect(self.reselect_clicked.emit)
        btn_layout.addWidget(self.reselect_btn)
        
        self.toggle_main_btn = QPushButton("隐藏主窗口")
        self.toggle_main_btn.setStyleSheet(btn_style)
        self.toggle_main_btn.clicked.connect(self.toggle_main_window)
        btn_layout.addWidget(self.toggle_main_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setStyleSheet(stop_style)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        btn_layout.addWidget(self.stop_btn)
        
        container_layout.addLayout(btn_layout)
        layout.addWidget(container)

    def toggle_main_window(self):
        if self.main_hidden:
            self.show_main_clicked.emit()
            self.toggle_main_btn.setText("隐藏主窗口")
            self.main_hidden = False
        else:
            self.hide_main_clicked.emit()
            self.toggle_main_btn.setText("显示主窗口")
            self.main_hidden = True

    def update_status(self, time_str, frames):
        self.time_label.setText(time_str)
        self.frame_label.setText(f"{frames} 帧")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            
    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def reset_state(self):
        self.main_hidden = False
        self.toggle_main_btn.setText("隐藏主窗口")

# ==========================================
# 区域选择后的确认面板
# ==========================================
class RegionConfirmPanel(QWidget):
    confirm_clicked = pyqtSignal()
    reselect_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()
    
    def __init__(self, region, parent=None):
        super().__init__(parent)
        self.region = region
        # 作为子控件，不需要 WindowStaysOnTopHint，但需要确保不被背景遮挡
        if parent:
            self.setWindowFlags(Qt.SubWindow)
        else:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            
        self.setFixedSize(320, 140)
        self.drag_pos = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                border: 2px solid #89b4fa;
                border-radius: 12px;
            }
            QLabel {
                color: #cdd6f4;
                font-family: "Microsoft YaHei";
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(15)
        container_layout.setContentsMargins(20, 20, 20, 20)
        
        # 信息
        w, h = self.region['width'], self.region['height']
        self.info = QLabel(f"已选择区域: {w} x {h}")
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        container_layout.addWidget(self.info)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        confirm_style = """
            QPushButton {
                background-color: #a6e3a1;
                color: #1e1e2e;
                border-radius: 6px;
                padding: 8px 30px;
                font-family: "Microsoft YaHei";
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #94e2d5; }
        """

        confirm = QPushButton("开始录制")
        confirm.setStyleSheet(confirm_style)
        confirm.clicked.connect(self.confirm_clicked.emit)
        btn_layout.addStretch()
        btn_layout.addWidget(confirm)
        btn_layout.addStretch()
        
        container_layout.addLayout(btn_layout)
        layout.addWidget(container)

    def update_region(self, region):
        self.region = region
        w, h = region['width'], region['height']
        self.info.setText(f"已选择区域: {w} x {h}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            
    def mouseReleaseEvent(self, event):
        self.drag_pos = None

# ==========================================
# 区域选择器 (全屏透明覆盖，支持拖拽调整)
# ==========================================
class RegionSelector(QDialog):
    region_selected = pyqtSignal(dict)
    
    # 调整模式枚举
    Mode_None = 0
    Mode_Move = 1
    Mode_Resize_TL = 2 # Top-Left
    Mode_Resize_T  = 3 # Top
    Mode_Resize_TR = 4 # Top-Right
    Mode_Resize_R  = 5 # Right
    Mode_Resize_BR = 6 # Bottom-Right
    Mode_Resize_B  = 7 # Bottom
    Mode_Resize_BL = 8 # Bottom-Left
    Mode_Resize_L  = 9 # Left

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True) # 启用鼠标追踪以更改光标
        
        # 计算所有显示器的虚拟桌面范围
        self.virtual_geometry = self._get_virtual_geometry()
        self.setGeometry(self.virtual_geometry)
        
        self.start_pos = None
        self.current_rect = QRect()
        self.selection_done = False # 是否已完成初步选择（进入调整模式）
        self.confirm_panel = None
        
        self.edit_mode = self.Mode_None
        self.drag_offset = None
        self.handle_size = 10 # 手柄大小
    
    def _get_virtual_geometry(self):
        """获取所有显示器组成的虚拟桌面范围"""
        screens = QApplication.screens()
        if not screens:
            return QApplication.primaryScreen().geometry()
        
        min_x = min(s.geometry().x() for s in screens)
        min_y = min(s.geometry().y() for s in screens)
        max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
        max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
        
        return QRect(min_x, min_y, max_x - min_x, max_y - min_y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制背景（挖空选区）
        bg_color = QColor(0, 0, 0, 120)
        region = QRegion(self.rect())
        if not self.current_rect.isEmpty():
            region = region.subtracted(QRegion(self.current_rect))
        
        path = QPainterPath()
        path.addRegion(region)
        painter.fillPath(path, bg_color)
        
        # 绘制选框
        if not self.current_rect.isEmpty():
            # 边框
            pen = QPen(QColor(0, 120, 215), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.current_rect)
            
            # 绘制尺寸文字
            txt = f"{self.current_rect.width()} x {self.current_rect.height()}"
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
            
            # 文字位置自适应
            txt_rect = painter.fontMetrics().boundingRect(txt)
            txt_x = self.current_rect.center().x() - txt_rect.width() // 2
            txt_y = self.current_rect.top() - 10
            if txt_y < 20: 
                txt_y = self.current_rect.bottom() + txt_rect.height() + 5
            painter.drawText(txt_x, txt_y, txt)

            # 如果已完成初步选择，绘制调整手柄
            if self.selection_done:
                self.draw_handles(painter)
        else:
            # 初始提示
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "拖动鼠标框选区域\n完成后可调整大小")

    def draw_handles(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        
        r = self.current_rect
        s = self.handle_size
        s2 = s // 2
        
        # 8个手柄坐标
        handles = [
            (r.left() - s2, r.top() - s2),     # TL
            (r.center().x() - s2, r.top() - s2), # T
            (r.right() - s2, r.top() - s2),    # TR
            (r.right() - s2, r.center().y() - s2), # R
            (r.right() - s2, r.bottom() - s2), # BR
            (r.center().x() - s2, r.bottom() - s2), # B
            (r.left() - s2, r.bottom() - s2),  # BL
            (r.left() - s2, r.center().y() - s2) # L
        ]
        
        for x, y in handles:
            painter.drawRect(x, y, s, s)

    def hit_test(self, pos):
        if self.current_rect.isEmpty(): return self.Mode_None
        
        r = self.current_rect
        s = self.handle_size
        s2 = s + 5 # 增加响应区域
        
        # 检查手柄
        if abs(pos.x() - r.left()) < s2 and abs(pos.y() - r.top()) < s2: return self.Mode_Resize_TL
        if abs(pos.x() - r.right()) < s2 and abs(pos.y() - r.top()) < s2: return self.Mode_Resize_TR
        if abs(pos.x() - r.right()) < s2 and abs(pos.y() - r.bottom()) < s2: return self.Mode_Resize_BR
        if abs(pos.x() - r.left()) < s2 and abs(pos.y() - r.bottom()) < s2: return self.Mode_Resize_BL
        
        if abs(pos.x() - r.center().x()) < s2 and abs(pos.y() - r.top()) < s2: return self.Mode_Resize_T
        if abs(pos.x() - r.right()) < s2 and abs(pos.y() - r.center().y()) < s2: return self.Mode_Resize_R
        if abs(pos.x() - r.center().x()) < s2 and abs(pos.y() - r.bottom()) < s2: return self.Mode_Resize_B
        if abs(pos.x() - r.left()) < s2 and abs(pos.y() - r.center().y()) < s2: return self.Mode_Resize_L
        
        if r.contains(pos): return self.Mode_Move
        
        return self.Mode_None

    def update_cursor(self, mode):
        cursors = {
            self.Mode_None: Qt.CrossCursor,
            self.Mode_Move: Qt.SizeAllCursor,
            self.Mode_Resize_TL: Qt.SizeFDiagCursor,
            self.Mode_Resize_BR: Qt.SizeFDiagCursor,
            self.Mode_Resize_TR: Qt.SizeBDiagCursor,
            self.Mode_Resize_BL: Qt.SizeBDiagCursor,
            self.Mode_Resize_T: Qt.SizeVerCursor,
            self.Mode_Resize_B: Qt.SizeVerCursor,
            self.Mode_Resize_L: Qt.SizeHorCursor,
            self.Mode_Resize_R: Qt.SizeHorCursor,
        }
        self.setCursor(cursors.get(mode, Qt.CrossCursor))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton: return
        
        if self.selection_done:
            # 调整模式
            self.edit_mode = self.hit_test(event.pos())
            if self.edit_mode == self.Mode_Move:
                self.drag_offset = event.pos() - self.current_rect.topLeft()
            elif self.edit_mode == self.Mode_None:
                # 点击外部，重新开始选择
                self.selection_done = False
                self.confirm_panel_hide()
                self.start_pos = event.pos()
                self.current_rect = QRect()
            else:
                self.start_pos = event.pos() # 用于计算偏移
                self.initial_rect = QRect(self.current_rect) # 记录调整前的矩形
        else:
            # 新建选区模式
            self.start_pos = event.pos()
            self.current_rect = QRect()
            
        self.update()

    def mouseMoveEvent(self, event):
        if not self.selection_done:
            if self.start_pos:
                self.current_rect = QRect(self.start_pos, event.pos()).normalized()
                self.update()
            return

        # 已完成选择，处理悬停光标或拖拽
        if event.buttons() & Qt.LeftButton:
            # 正在拖拽
            if self.edit_mode == self.Mode_Move:
                if self.drag_offset:
                    new_top_left = event.pos() - self.drag_offset
                    self.current_rect.moveTopLeft(new_top_left)
                    # 确认面板跟随
                    self.update_confirm_panel_pos()
            elif self.edit_mode != self.Mode_None:
                self.handle_resize(event.pos())
                self.update_confirm_panel_pos()
            
            self.update()
        else:
            # 悬停更新光标
            mode = self.hit_test(event.pos())
            self.update_cursor(mode)

    def handle_resize(self, pos):
        r = self.initial_rect
        mode = self.edit_mode
        
        # 简单的逻辑：根据模式调整对应的边
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        
        dx = pos.x() - self.start_pos.x()
        dy = pos.y() - self.start_pos.y()
        
        if mode == self.Mode_Resize_L or mode == self.Mode_Resize_TL or mode == self.Mode_Resize_BL:
            left += dx
        if mode == self.Mode_Resize_R or mode == self.Mode_Resize_TR or mode == self.Mode_Resize_BR:
            right += dx
        if mode == self.Mode_Resize_T or mode == self.Mode_Resize_TL or mode == self.Mode_Resize_TR:
            top += dy
        if mode == self.Mode_Resize_B or mode == self.Mode_Resize_BL or mode == self.Mode_Resize_BR:
            bottom += dy
            
        self.current_rect = QRect(QPoint(left, top), QPoint(right, bottom)).normalized()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton: return
        
        if not self.selection_done:
            # 完成框选
            if self.current_rect.width() > 10 and self.current_rect.height() > 10:
                self.selection_done = True
                self.show_confirm_panel()
            else:
                self.start_pos = None
                self.current_rect = QRect()
        else:
            # 完成调整
            self.edit_mode = self.Mode_None
            self.drag_offset = None
            if self.current_rect.width() > 10 and self.current_rect.height() > 10:
                if not self.confirm_panel or not self.confirm_panel.isVisible():
                    self.show_confirm_panel()
        
        self.update()

    def show_confirm_panel(self):
        if not self.confirm_panel:
            # 传递 self 作为 parent
            self.confirm_panel = RegionConfirmPanel(self.get_current_region(), parent=self)
            self.confirm_panel.confirm_clicked.connect(self.on_confirm)
            self.confirm_panel.reselect_clicked.connect(self.on_reselect)
            self.confirm_panel.cancel_clicked.connect(self.on_cancel)
        
        self.update_confirm_panel_region()
        self.update_confirm_panel_pos()
        self.confirm_panel.show()

    def confirm_panel_hide(self):
        if self.confirm_panel: self.confirm_panel.hide()

    def update_confirm_panel_region(self):
        if self.confirm_panel:
            self.confirm_panel.update_region(self.get_current_region())

    def update_confirm_panel_pos(self):
        if not self.confirm_panel: return
        
        panel_w = self.confirm_panel.width()
        panel_h = self.confirm_panel.height()
        
        # 默认放在底部中间
        x = self.current_rect.center().x() - panel_w // 2
        y = self.current_rect.bottom() + 15
        
        # 使用虚拟桌面范围进行边界检查
        vg = self.virtual_geometry
        
        # 边界检查
        if y + panel_h > vg.bottom():
            y = self.current_rect.top() - panel_h - 15
        if y < vg.top(): # 如果上方也放不下，就放中间
            y = self.current_rect.center().y() - panel_h // 2
            
        if x < vg.left(): x = vg.left() + 10
        if x + panel_w > vg.right(): x = vg.right() - panel_w - 10
            
        self.confirm_panel.move(x, y)

    def get_current_region(self):
        # 将窗口相对坐标转换为全局屏幕坐标
        # 因为窗口可能从负坐标开始（多显示器），需要加上窗口的偏移
        global_left = self.current_rect.left() + self.virtual_geometry.left()
        global_top = self.current_rect.top() + self.virtual_geometry.top()
        return {
            "left": global_left,
            "top": global_top,
            "width": self.current_rect.width(),
            "height": self.current_rect.height()
        }

    def on_confirm(self):
        self.confirm_panel.close()
        self.region_selected.emit(self.get_current_region())
        self.close()
        
    def on_reselect(self):
        self.confirm_panel.hide()
        self.selection_done = False
        self.start_pos = None
        self.current_rect = QRect()
        self.update()
        self.setCursor(Qt.CrossCursor)
        
    def on_cancel(self):
        if self.confirm_panel: self.confirm_panel.close()
        self.close()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.on_cancel()

# ==========================================
# 后台线程
# ==========================================
class AudioRecordThread(QThread):
    """音频录制线程 - 使用 pyaudiowpatch 录制系统音频（WASAPI loopback）"""
    def __init__(self, sample_rate=44100, record_system=True, record_mic=True):
        super().__init__()
        self.sample_rate = sample_rate
        self.record_system = record_system
        self.record_mic = record_mic
        self.is_recording = False
        self.system_audio_data = []
        self.mic_audio_data = []
        self.system_channels = 2
        self.mic_channels = 1
        
    def run(self):
        self.is_recording = True
        self.system_audio_data = []
        self.mic_audio_data = []
        
        p = None
        system_stream = None
        mic_stream = None
        
        try:
            # 使用 pyaudiowpatch 录制系统音频（WASAPI loopback）
            if self.record_system and SYSTEM_AUDIO_AVAILABLE:
                try:
                    p = pyaudio.PyAudio()
                    
                    # 获取默认的 WASAPI loopback 设备（系统音频输出）
                    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                    
                    # 查找对应的 loopback 设备
                    loopback_device = None
                    for i in range(p.get_device_count()):
                        dev = p.get_device_info_by_index(i)
                        if dev["name"].endswith("[Loopback]") or "loopback" in dev["name"].lower():
                            if default_speakers["name"] in dev["name"]:
                                loopback_device = dev
                                break
                    
                    # 如果没找到匹配的，使用任意 loopback 设备
                    if loopback_device is None:
                        for i in range(p.get_device_count()):
                            dev = p.get_device_info_by_index(i)
                            if "loopback" in dev["name"].lower():
                                loopback_device = dev
                                break
                    
                    if loopback_device:
                        self.system_channels = loopback_device["maxInputChannels"]
                        system_sample_rate = int(loopback_device["defaultSampleRate"])
                        
                        def system_callback(in_data, frame_count, time_info, status):
                            if self.is_recording:
                                audio_data = np.frombuffer(in_data, dtype=np.float32)
                                audio_data = audio_data.reshape(-1, self.system_channels)
                                self.system_audio_data.append(audio_data.copy())
                            return (in_data, pyaudio.paContinue)
                        
                        system_stream = p.open(
                            format=pyaudio.paFloat32,
                            channels=self.system_channels,
                            rate=system_sample_rate,
                            input=True,
                            input_device_index=loopback_device["index"],
                            frames_per_buffer=512,
                            stream_callback=system_callback
                        )
                        system_stream.start_stream()
                        print(f"System audio recording started: {loopback_device['name']} ({self.system_channels} ch, {system_sample_rate} Hz)")
                    else:
                        print("No WASAPI loopback device found for system audio")
                        
                except Exception as e:
                    print(f"System audio error: {e}")
            
            # 使用 sounddevice 录制麦克风
            if self.record_mic and AUDIO_AVAILABLE:
                try:
                    default_input = sd.query_devices(kind='input')
                    self.mic_channels = min(2, default_input['max_input_channels'])
                    
                    def mic_callback(indata, frames, time_info, status):
                        if self.is_recording:
                            self.mic_audio_data.append(indata.copy())
                    
                    if self.mic_channels > 0:
                        mic_stream = sd.InputStream(
                            samplerate=self.sample_rate,
                            channels=self.mic_channels,
                            callback=mic_callback
                        )
                        mic_stream.start()
                        print(f"Microphone recording started ({self.mic_channels} channels)")
                except Exception as e:
                    print(f"Microphone error: {e}")
            
            # 等待录制结束
            while self.is_recording:
                time.sleep(0.1)
                
        except Exception as e:
            print(f"Audio record error: {e}")
        finally:
            # 关闭所有流
            if system_stream:
                try:
                    system_stream.stop_stream()
                    system_stream.close()
                except:
                    pass
            if mic_stream:
                try:
                    mic_stream.stop()
                    mic_stream.close()
                except:
                    pass
            if p:
                try:
                    p.terminate()
                except:
                    pass
    
    def stop(self):
        self.is_recording = False
    
    def save_to_file(self, filepath):
        """保存音频到文件（混合系统音频和麦克风）"""
        try:
            audio_parts = []
            
            def ensure_stereo(audio):
                """确保音频是双声道"""
                if audio.ndim == 1:
                    return np.column_stack([audio, audio])
                elif audio.shape[1] == 1:
                    return np.column_stack([audio[:, 0], audio[:, 0]])
                return audio
            
            # 处理系统音频
            if self.system_audio_data:
                system_audio = np.concatenate(self.system_audio_data, axis=0)
                system_audio = ensure_stereo(system_audio)
                audio_parts.append(system_audio)
                print(f"System audio: {len(system_audio)} samples")
            
            # 处理麦克风音频
            if self.mic_audio_data:
                mic_audio = np.concatenate(self.mic_audio_data, axis=0)
                mic_audio = ensure_stereo(mic_audio)
                audio_parts.append(mic_audio)
                print(f"Mic audio: {len(mic_audio)} samples")
            
            if not audio_parts:
                return None
            
            # 混合音频
            if len(audio_parts) == 1:
                mixed = audio_parts[0]
            else:
                # 对齐长度
                min_len = min(len(p) for p in audio_parts)
                aligned = [p[:min_len] for p in audio_parts]
                # 混合（平均）
                mixed = np.mean(aligned, axis=0).astype(np.float32)
            
            sf.write(filepath, mixed, self.sample_rate)
            return filepath
        except Exception as e:
            print(f"Save audio error: {e}")
            return None

class RecordThread(QThread):
    frame_captured = pyqtSignal(int)
    recording_stopped = pyqtSignal()
    
    def __init__(self, fps, region=None, record_audio=False):
        super().__init__()
        self.fps = fps
        self.region = region
        self.record_audio = record_audio and AUDIO_AVAILABLE
        self.is_recording = False
        self.frames = []
        self.audio_thread = None
        self.audio_file = None
        
    def run(self):
        self.is_recording = True
        self.frames = []
        count = 0
        
        # 启动音频录制
        if self.record_audio:
            self.audio_thread = AudioRecordThread()
            self.audio_thread.start()
        
        with mss.mss() as sct:
            monitor = self.region if self.region else sct.monitors[1]
            interval = 1.0 / self.fps
            
            while self.is_recording:
                start = time.time()
                
                try:
                    img = sct.grab(monitor)
                    frame = np.array(img)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    self.frames.append(frame)
                    count += 1
                    self.frame_captured.emit(count)
                except Exception as e:
                    print(f"Record error: {e}")
                
                elapsed = time.time() - start
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        
        # 停止音频录制并保存
        if self.audio_thread:
            self.audio_thread.stop()
            self.audio_thread.wait()
            # 保存音频到临时文件
            self.audio_file = os.path.join(tempfile.gettempdir(), f"screen_rec_audio_{int(time.time())}.wav")
            self.audio_thread.save_to_file(self.audio_file)
                    
        self.recording_stopped.emit()

    def stop(self):
        self.is_recording = False
    
    def get_audio_file(self):
        return self.audio_file

class ExportThread(QThread):
    progress_updated = pyqtSignal(int)
    export_finished = pyqtSignal(bool, str)
    
    def __init__(self, frames, path, fps, fmt, gif_fps=10, audio_file=None):
        super().__init__()
        self.frames = frames
        self.path = path
        self.fps = fps
        self.fmt = fmt
        self.gif_fps = gif_fps
        self.audio_file = audio_file
        
    def run(self):
        try:
            total = len(self.frames)
            if total == 0:
                self.export_finished.emit(False, "没有录制到任何帧")
                return

            if self.fmt == 'gif':
                frames_rgb = []
                step = max(1, self.fps // self.gif_fps)
                selected = self.frames[::step]
                count = len(selected)
                
                for i, frame in enumerate(selected):
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    # 限制尺寸防止内存爆炸
                    h, w = rgb.shape[:2]
                    if w > 1000:
                        scale = 1000 / w
                        rgb = cv2.resize(rgb, (0, 0), fx=scale, fy=scale)
                    frames_rgb.append(rgb)
                    self.progress_updated.emit(int((i+1)/count * 100))
                    
                imageio.mimsave(self.path, frames_rgb, fps=self.gif_fps)
            else:
                h, w = self.frames[0].shape[:2]
                
                # 如果有音频，使用 ffmpeg 合并
                if self.audio_file and os.path.exists(self.audio_file):
                    self._export_with_audio(w, h, total)
                else:
                    self._export_video_only(w, h, total)
                
            self.export_finished.emit(True, self.path)
        except Exception as e:
            self.export_finished.emit(False, str(e))
    
    def _export_video_only(self, w, h, total):
        """仅导出视频"""
        fourcc_map = {
            'mp4': cv2.VideoWriter_fourcc(*'mp4v'),
            'avi': cv2.VideoWriter_fourcc(*'XVID'),
            'webm': cv2.VideoWriter_fourcc(*'VP80')
        }
        fourcc = fourcc_map.get(self.fmt, fourcc_map['mp4'])
        out = cv2.VideoWriter(self.path, fourcc, self.fps, (w, h))
        
        for i, frame in enumerate(self.frames):
            out.write(frame)
            self.progress_updated.emit(int((i+1)/total * 100))
        out.release()
    
    def _export_with_audio(self, w, h, total):
        """使用 ffmpeg 合并音视频"""
        # 先导出临时视频
        temp_video = os.path.join(tempfile.gettempdir(), f"temp_video_{int(time.time())}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video, fourcc, self.fps, (w, h))
        
        for i, frame in enumerate(self.frames):
            out.write(frame)
            self.progress_updated.emit(int((i+1)/total * 80))  # 80% 用于视频
        out.release()
        
        # 使用 ffmpeg 合并音视频
        try:
            # 尝试使用 imageio-ffmpeg 提供的 ffmpeg
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except:
            ffmpeg_path = "ffmpeg"  # 使用系统 ffmpeg
        
        cmd = [
            ffmpeg_path,
            '-y',  # 覆盖输出
            '-i', temp_video,
            '-i', self.audio_file,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-shortest',  # 以较短的流为准
            self.path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.progress_updated.emit(100)
            
            # 清理临时文件
            if os.path.exists(temp_video):
                os.remove(temp_video)
            if os.path.exists(self.audio_file):
                os.remove(self.audio_file)
                
            if result.returncode != 0:
                # ffmpeg 失败，回退到仅视频
                import shutil
                shutil.copy(temp_video, self.path)
        except Exception as e:
            print(f"FFmpeg merge error: {e}")
            # 回退：直接使用视频文件
            import shutil
            if os.path.exists(temp_video):
                shutil.copy(temp_video, self.path)

# ==========================================
# 主窗口
# ==========================================
class ScreenRecorder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.is_recording = False
        self.record_thread = None
        self.record_time = 0
        self.monitors = []
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        
        self.floating_panel = FloatingControlPanel()
        self.floating_panel.stop_clicked.connect(self.stop_recording)
        self.floating_panel.reselect_clicked.connect(self.reselect_region)
        self.floating_panel.hide_main_clicked.connect(self.hide)
        self.floating_panel.show_main_clicked.connect(self.show)
        
        self.init_monitors()
        self.init_ui()
        self.apply_style()

    def init_monitors(self):
        with mss.mss() as sct:
            self.monitors = sct.monitors

    def init_ui(self):
        self.setWindowTitle("屏幕录制工具 Pro")
        self.setFixedSize(650, 800) # 增大窗口
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 40, 30, 40)
        
        # 标题
        title = QLabel("屏幕录制工具")
        title.setFont(QFont("Microsoft YaHei", 28, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #89b4fa; letter-spacing: 2px;")
        main_layout.addWidget(title)
        
        # 选项卡
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- 录制页 ---
        rec_page = QWidget()
        rec_layout = QVBoxLayout(rec_page)
        rec_layout.setSpacing(25)
        rec_layout.setContentsMargins(20, 30, 20, 30)
        
        # 模式选择卡片
        mode_box = self.create_card("录制模式")
        mode_inner = QVBoxLayout(mode_box)
        
        self.mode_group = QButtonGroup()
        
        # 自定义区域 (大按钮)
        self.btn_custom = QRadioButton("区域录制")
        self.btn_custom.setChecked(True)
        self.mode_group.addButton(self.btn_custom, 0)
        mode_inner.addWidget(self.btn_custom)
        
        self.btn_select_area = QPushButton("点击框选区域")
        self.btn_select_area.setFixedHeight(60)
        self.btn_select_area.setCursor(Qt.PointingHandCursor)
        self.btn_select_area.clicked.connect(self.start_selection)
        mode_inner.addWidget(self.btn_select_area)
        
        mode_inner.addSpacing(10)
        
        # 全屏/显示器
        hbox_mon = QHBoxLayout()
        self.btn_full = QRadioButton("全屏/显示器")
        self.mode_group.addButton(self.btn_full, 1)
        hbox_mon.addWidget(self.btn_full)
        
        self.combo_mon = QComboBox()
        for i, m in enumerate(self.monitors[1:], 1):
            self.combo_mon.addItem(f"显示器 {i} ({m['width']}x{m['height']})")
        hbox_mon.addWidget(self.combo_mon, 1)
        mode_inner.addLayout(hbox_mon)
        
        rec_layout.addWidget(mode_box)
        
        # 参数设置卡片
        set_box = self.create_card("录制参数")
        set_inner = QHBoxLayout(set_box)
        
        set_inner.addWidget(QLabel("帧率:"))
        self.combo_fps = QComboBox()
        self.combo_fps.addItems(["30 FPS", "60 FPS", "24 FPS", "15 FPS"])
        set_inner.addWidget(self.combo_fps, 1)
        
        set_inner.addSpacing(20)
        self.check_audio = QCheckBox("录制音频")
        self.check_audio.setChecked(True)  # 默认勾选
        self.check_audio.setToolTip("录制系统音频（网易云、网页等）+ 麦克风")
        set_inner.addWidget(self.check_audio)
        
        rec_layout.addWidget(set_box)
        
        # 状态卡片
        stat_box = self.create_card("当前状态")
        stat_inner = QVBoxLayout(stat_box)
        
        self.lbl_time = QLabel("00:00:00")
        self.lbl_time.setAlignment(Qt.AlignCenter)
        self.lbl_time.setFont(QFont("Consolas", 48, QFont.Bold))
        self.lbl_time.setStyleSheet("color: #89b4fa;")
        stat_inner.addWidget(self.lbl_time)
        
        self.lbl_frames = QLabel("等待开始...")
        self.lbl_frames.setAlignment(Qt.AlignCenter)
        self.lbl_frames.setStyleSheet("color: #6c7086; font-size: 14px;")
        stat_inner.addWidget(self.lbl_frames)
        
        rec_layout.addWidget(stat_box)
        
        # 底部按钮
        self.btn_start = QPushButton("开始录制")
        self.btn_start.setFixedHeight(60)
        self.btn_start.clicked.connect(self.on_start_click)
        self.btn_start.setObjectName("btn_start") # 用于样式
        rec_layout.addWidget(self.btn_start)
        
        self.tabs.addTab(rec_page, "录制")
        
        # --- 导出页 ---
        exp_page = QWidget()
        exp_layout = QVBoxLayout(exp_page)
        exp_layout.setSpacing(25)
        exp_layout.setContentsMargins(20, 30, 20, 30)
        
        fmt_box = self.create_card("导出设置")
        fmt_inner = QVBoxLayout(fmt_box)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("格式:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["MP4", "GIF", "AVI", "WebM"])
        self.combo_fmt.currentTextChanged.connect(self._on_format_changed)
        row1.addWidget(self.combo_fmt, 1)
        fmt_inner.addLayout(row1)
        
        # 帧率提示（MP4/AVI/WebM 使用录制帧率）
        self.lbl_fps_info = QLabel("输出帧率: 使用录制时设置的帧率")
        self.lbl_fps_info.setStyleSheet("color: #6c7086; font-size: 12px;")
        fmt_inner.addWidget(self.lbl_fps_info)
        
        row2 = QHBoxLayout()
        self.lbl_gif_fps = QLabel("GIF帧率:")
        row2.addWidget(self.lbl_gif_fps)
        self.spin_gif_fps = QSpinBox()
        self.spin_gif_fps.setRange(1, 30)
        self.spin_gif_fps.setValue(10)
        self.spin_gif_fps.setSuffix(" fps")
        self.spin_gif_fps.setToolTip("GIF 文件的输出帧率（较低帧率可减小文件大小）")
        row2.addWidget(self.spin_gif_fps, 1)
        fmt_inner.addLayout(row2)
        
        # 初始隐藏 GIF 帧率设置（默认是 MP4）
        self.lbl_gif_fps.hide()
        self.spin_gif_fps.hide()
        
        exp_layout.addWidget(fmt_box)
        
        path_box = self.create_card("保存位置")
        path_inner = QHBoxLayout(path_box)
        
        self.lbl_path = QLabel(str(Path.home() / "Videos"))
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("background: #313244; padding: 10px; border-radius: 5px;")
        path_inner.addWidget(self.lbl_path, 1)
        
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self.browse_path)
        path_inner.addWidget(btn_browse)
        
        exp_layout.addWidget(path_box)
        
        # 进度
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(30)
        exp_layout.addWidget(self.progress)
        
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        exp_layout.addWidget(self.lbl_status)
        
        self.btn_export = QPushButton("导出文件")
        self.btn_export.setFixedHeight(60)
        self.btn_export.clicked.connect(self.start_export)
        self.btn_export.setEnabled(False)
        self.btn_export.setObjectName("btn_export")
        exp_layout.addWidget(self.btn_export)
        
        exp_layout.addStretch()
        self.tabs.addTab(exp_page, "导出")
        
        # 关于页
        about_scroll = QScrollArea()
        about_scroll.setWidgetResizable(True)
        about_scroll.setStyleSheet("border: none; background-color: transparent;")
        
        about_content = QWidget()
        about_layout = QVBoxLayout(about_content)
        about_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        about_layout.setSpacing(20)
        about_layout.setContentsMargins(30, 40, 30, 40)
        
        # 标题
        about_title = QLabel("屏幕录制工具 Pro v2.0")
        about_title.setFont(QFont("Microsoft YaHei", 22, QFont.Bold))
        about_title.setAlignment(Qt.AlignCenter)
        about_title.setStyleSheet("color: #89b4fa;")
        about_layout.addWidget(about_title)
        
        # 描述
        desc = QLabel("功能特点：\n• 区域/全屏录制\n• 选区拖拽调整\n• MP4/GIF/AVI/WebM 导出\n• 悬浮控制面板")
        desc.setAlignment(Qt.AlignCenter)
        desc.setFont(QFont("Microsoft YaHei", 12))
        desc.setStyleSheet("color: #cdd6f4; line-height: 1.5;")
        about_layout.addWidget(desc)
        
        # 收款码
        shou_path = resource_path("SHOU.png")
        pixmap = QPixmap()
        if os.path.exists(shou_path):
            pixmap.load(shou_path)
            
        if not pixmap.isNull():
            # 缩放图片以适应窗口
            scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_img = QLabel()
            lbl_img.setPixmap(scaled_pixmap)
            lbl_img.setAlignment(Qt.AlignCenter)
            about_layout.addWidget(lbl_img)
        
        lbl_tip = QLabel("请作者吃辣条")
        lbl_tip.setAlignment(Qt.AlignCenter)
        lbl_tip.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 14px;")
        about_layout.addWidget(lbl_tip)
        
        about_scroll.setWidget(about_content)
        self.tabs.addTab(about_scroll, "关于")
        
        # 设置图标
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            svg_path = resource_path("icon.svg")
            if os.path.exists(svg_path):
                self.setWindowIcon(QIcon(svg_path))

    def create_card(self, title):
        group = QGroupBox(title)
        group.setFont(QFont("Microsoft YaHei", 12))
        return group

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #cdd6f4; font-family: "Microsoft YaHei"; font-size: 14px; }
            
            QTabWidget::pane { border: none; background: #1e1e2e; }
            QTabBar::tab {
                background: #313244; color: #a6adc8;
                padding: 12px 30px; margin-right: 5px;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
            }
            QTabBar::tab:selected { background: #89b4fa; color: #1e1e2e; font-weight: bold; }
            
            QGroupBox {
                border: 1px solid #45475a; border-radius: 8px;
                margin-top: 25px; font-weight: bold; color: #89b4fa;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 5px; }
            
            QPushButton {
                background-color: #313244; border: 1px solid #45475a;
                border-radius: 8px; padding: 5px;
            }
            QPushButton:hover { background-color: #45475a; border-color: #585b70; }
            
            QPushButton#btn_start {
                background-color: #a6e3a1; color: #1e1e2e;
                font-size: 18px; font-weight: bold; border: none;
            }
            QPushButton#btn_start:hover { background-color: #94e2d5; }
            
            QPushButton#btn_export {
                background-color: #f9e2af; color: #1e1e2e;
                font-size: 18px; font-weight: bold; border: none;
            }
            QPushButton#btn_export:disabled { background-color: #45475a; color: #6c7086; }
            
            QComboBox {
                background: #313244; border: 1px solid #45475a;
                border-radius: 6px; padding: 8px; min-height: 25px;
            }
            QComboBox::drop-down { border: none; width: 30px; }
            QComboBox QAbstractItemView {
                background: #313244; selection-background-color: #585b70;
            }
            
            QRadioButton { spacing: 10px; }
            QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #6c7086; }
            QRadioButton::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
            
            QProgressBar {
                background: #313244; border-radius: 5px; text-align: center;
            }
            QProgressBar::chunk { background: #89b4fa; border-radius: 5px; }
        """)

    # 逻辑部分
    def on_start_click(self):
        if self.btn_custom.isChecked():
            self.start_selection()
        else:
            idx = self.combo_mon.currentIndex()
            region = self.monitors[idx + 1]
            self.start_recording(region)

    def start_selection(self):
        self.hide()
        # 延时确保窗口完全隐藏
        QTimer.singleShot(200, self._show_selector)

    def _show_selector(self):
        self.selector = RegionSelector()
        self.selector.region_selected.connect(self.start_recording)
        self.selector.rejected.connect(self.show)
        self.selector.exec_()

    def reselect_region(self):
        # 停止当前录制，保留帧，然后重选
        self.stop_recording(finish=False)
        self.floating_panel.hide()
        self.start_selection()

    def start_recording(self, region):
        # 如果是新的录制（不是重选继续），清空帧
        if not self.frames:
            self.frames = []
            self.record_time = 0
            self.audio_file = None
            
        self.is_recording = True
        fps = int(self.combo_fps.currentText().split()[0])
        record_audio = self.check_audio.isChecked()
        
        self.record_thread = RecordThread(fps, region, record_audio=record_audio)
        self.record_thread.frame_captured.connect(self.on_frame_captured)
        self.record_thread.recording_stopped.connect(self.on_recording_stopped)
        self.record_thread.start()
        
        self.timer.start(1000)
        self.update_ui_state(recording=True)
        
        # 显示悬浮窗
        self.floating_panel.update_status(self.format_time(self.record_time), len(self.frames))
        self.floating_panel.show()
        
        # 如果不是全屏模式，主窗口隐藏
        if self.btn_custom.isChecked():
            self.hide()
        else:
            self.showMinimized()

    def stop_recording(self, finish=True):
        if self.record_thread:
            self.record_thread.stop()
            self.record_thread.wait()
            self.frames.extend(self.record_thread.frames)
            # 保存音频文件路径
            self.audio_file = self.record_thread.get_audio_file()
            
        self.timer.stop()
        self.is_recording = False
        self.update_ui_state(recording=False)
        self.floating_panel.hide()
        self.showNormal()
        
        if finish and self.frames:
            self.tabs.setCurrentIndex(1)
            self.btn_export.setEnabled(True)
            msg = f"录制结束，共 {len(self.frames)} 帧"
            if self.audio_file:
                msg += "\n已录制音频"
            msg += "\n请前往导出页保存文件"
            QMessageBox.information(self, "完成", msg)

    def on_frame_captured(self, count):
        total = len(self.frames) + count
        self.lbl_frames.setText(f"已录制: {total} 帧")
        self.floating_panel.update_status(self.format_time(self.record_time), total)

    def on_recording_stopped(self):
        pass

    def update_time(self):
        self.record_time += 1
        time_str = self.format_time(self.record_time)
        self.lbl_time.setText(time_str)
        
    def format_time(self, seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def update_ui_state(self, recording):
        self.btn_start.setEnabled(not recording)
        self.btn_start.setText("录制中..." if recording else "开始录制")
        self.btn_start.setStyleSheet(f"""
            QPushButton#btn_start {{
                background-color: {'#ff5555' if recording else '#a6e3a1'};
                color: #1e1e2e; font-size: 18px; font-weight: bold; border: none;
            }}
        """)
        
    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存路径")
        if path: self.lbl_path.setText(path)
    
    def _on_format_changed(self, fmt):
        """格式切换时更新 UI"""
        is_gif = fmt.lower() == 'gif'
        self.lbl_gif_fps.setVisible(is_gif)
        self.spin_gif_fps.setVisible(is_gif)
        
        if is_gif:
            self.lbl_fps_info.setText("GIF 不支持音频，帧率可单独设置")
        else:
            fps = self.combo_fps.currentText()
            self.lbl_fps_info.setText(f"输出帧率: {fps}（录制时设置）")

    def start_export(self):
        if not self.frames: return
        
        fmt = self.combo_fmt.currentText().lower()
        ext = fmt
        path = os.path.join(self.lbl_path.text(), f"Rec_{int(time.time())}.{ext}")
        
        fps = int(self.combo_fps.currentText().split()[0])
        gif_fps = self.spin_gif_fps.value()
        
        # 获取音频文件（如果有）
        audio_file = getattr(self, 'audio_file', None)
        # GIF 不支持音频
        if fmt == 'gif':
            audio_file = None
        
        self.btn_export.setEnabled(False)
        self.lbl_status.setText("正在导出...")
        self.progress.setValue(0)
        
        self.exp_thread = ExportThread(self.frames, path, fps, fmt, gif_fps, audio_file=audio_file)
        self.exp_thread.progress_updated.connect(self.progress.setValue)
        self.exp_thread.export_finished.connect(self.on_export_done)
        self.exp_thread.start()

    def on_export_done(self, success, msg):
        self.btn_export.setEnabled(True)
        self.lbl_status.setText("导出完成" if success else "导出失败")
        if success:
            QMessageBox.information(self, "成功", f"文件已保存:\n{msg}")
        else:
            QMessageBox.critical(self, "错误", msg)

if __name__ == "__main__":
    # Windows 任务栏图标需要设置 AppUserModelID
    try:
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID('ScreenRecorder.App')
    except:
        pass
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 设置应用级别图标（任务栏图标）
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    win = ScreenRecorder()
    win.show()
    sys.exit(app.exec_())

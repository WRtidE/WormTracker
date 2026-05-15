import sys
import cv2
import numpy as np
import os
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, 
                             QVBoxLayout, QHBoxLayout, QLCDNumber, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QSizePolicy, 
                             QPushButton, QFileDialog, QMessageBox, QGroupBox,
                             QStatusBar, QFormLayout, QSpinBox, QDoubleSpinBox,
                             QTabWidget)
from PyQt6.QtGui import QImage, QPixmap, QColor, QFont, QIcon
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# ==========================================================
# 🟢 从 counter.py 导入算法核心
# ==========================================================
from counter import (
    get_interpolated_grid, detect_worms, update_tracks, count_crossings, draw_dashboard,
    NUM_CHANNELS, X_MARGIN, WALL_RATIO, TRIPWIRE_RATIO, MIN_AREA, 
    BG_HISTORY, INIT_FRAME_INDEX, PANIC_NOISE_RATIO, GRID_MUTATION_TOLERANCE, 
    COOLDOWN_FRAMES, ROI_MASK_TOP_RATIO, ROI_MASK_BOTTOM_RATIO
)

# ==========================================================
# 🧵 视频处理线程类
# ==========================================================
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray, np.ndarray)
    update_counts_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()

    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path  
        self.is_running = True        
        self.is_paused = False    

        # 💡 精简后的动态参数字典
        self.algo_params = {
            'num_channels': NUM_CHANNELS,
            'tripwire_ratio': TRIPWIRE_RATIO,
            'min_area': MIN_AREA,
            'mask_top_ratio': ROI_MASK_TOP_RATIO,
            'mask_bottom_ratio': ROI_MASK_BOTTOM_RATIO
        }

    def update_param(self, key, value):
        self.algo_params[key] = value

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened(): return

        backSub = cv2.createBackgroundSubtractorMOG2(history=BG_HISTORY, varThreshold=16, detectShadows=False)
        
        # 💡 初始化计数器，动态适应当前的通道数量
        counts = {label: 0 for label in range(1, self.algo_params['num_channels'] + 1)}
        
        active_worms, cross_cooldown = {}, {}
        next_worm_id, frame_idx = 0, 0
        base_channel_width, grid_data, tripwire_y, panic_cooldown = None, None, 0, 0

        while cap.isOpened() and self.is_running:
            if self.is_paused:
                self.msleep(50) 
                continue

            ret, frame = cap.read()
            if not ret: break 
            frame_idx += 1
            is_panic_now = False
            
            # 💡 动态同步通道数量，确保如果在运行中被修改，字典不会报错
            current_channels = self.algo_params['num_channels']
            for i in range(1, current_channels + 1):
                if i not in counts: counts[i] = 0

            try:
                # 使用动态的 num_channels，而壁宽等使用全局默认常量
                grid_data = get_interpolated_grid(frame, current_channels, X_MARGIN, wall_ratio=WALL_RATIO)
                if base_channel_width is None and frame_idx >= INIT_FRAME_INDEX:
                    base_channel_width = grid_data['channel_width']
                if base_channel_width is not None:
                    mutation = abs(grid_data['channel_width'] - base_channel_width) / base_channel_width
                    if mutation > GRID_MUTATION_TOLERANCE: is_panic_now = True
                tripwire_y = int(frame.shape[0] * self.algo_params['tripwire_ratio'])
            except Exception: is_panic_now = True

            roi_mask_top = int(frame.shape[0] * self.algo_params['mask_top_ratio'])
            roi_mask_bottom = int(frame.shape[0] * self.algo_params['mask_bottom_ratio'])

            if frame_idx > INIT_FRAME_INDEX:
                centroids, fg_mask, noise_ratio, raw_fg = detect_worms(
                    frame, backSub, grid_data, self.algo_params['min_area'],
                    roi_mask_top=roi_mask_top, roi_mask_bottom=roi_mask_bottom)
                if noise_ratio > PANIC_NOISE_RATIO: is_panic_now = True
            else: raw_fg = None
                
            if is_panic_now: panic_cooldown = COOLDOWN_FRAMES

            if panic_cooldown > 0:
                panic_cooldown -= 1
                active_worms.clear(); cross_cooldown.clear()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                backSub.apply(blur, learningRate=0.1) 
                display_frame = draw_dashboard(frame, counts, grid_data, {}, tripwire_y, None, is_panic=True, cooldown_rem=panic_cooldown, mask_top=roi_mask_top, mask_bottom=roi_mask_bottom)
            elif frame_idx > INIT_FRAME_INDEX:
                active_worms, next_worm_id, movements, cross_cooldown = update_tracks(centroids, active_worms, next_worm_id, cross_cooldown)
                counts, cross_cooldown = count_crossings(active_worms, counts, grid_data['channel_bounds'], tripwire_y, cross_cooldown)
                display_frame = draw_dashboard(frame, counts, grid_data, active_worms, tripwire_y, None, mask_top=roi_mask_top, mask_bottom=roi_mask_bottom)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                backSub.apply(blur, learningRate=0.05)
                display_frame = draw_dashboard(frame, counts, grid_data, {}, tripwire_y, None, mask_top=roi_mask_top, mask_bottom=roi_mask_bottom)

            mask_frame = raw_fg if raw_fg is not None else np.zeros(frame.shape[:2], dtype=np.uint8)
            self.change_pixmap_signal.emit(display_frame.copy(), mask_frame.copy())
            self.update_counts_signal.emit(counts)
            QThread.msleep(1)

        cap.release()
        if self.is_running:
            self.finished_signal.emit()

    def toggle_pause(self): self.is_paused = not self.is_paused
    def stop(self): self.is_running = False; self.wait()


# ==========================================================
# 🌟 核心 UI 界面类 (极简 3 参数版)
# ==========================================================
class WormCounterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WormTrack Pro - 自动化线虫计数系统 v5.2 (Minimalist)")
        self.setMinimumSize(800, 400)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; font-family: 'Segoe UI', Arial; }
            QGroupBox { border: 2px solid #313244; border-radius: 8px; margin-top: 15px; font-size: 14px; font-weight: bold; color: #a6adc8; }
            QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 5px; }
            QPushButton { background-color: #313244; color: #cdd6f4; border: none; border-radius: 6px; padding: 10px; font-weight: bold; font-size: 14px; outline: none; }
            QPushButton:hover { background-color: #45475a; }
            QPushButton:pressed { background-color: #585b70; }
            QPushButton:disabled { background-color: #181825; color: #585b70; border: 1px solid #313244; }
            QSpinBox, QDoubleSpinBox { background-color: #11111b; color: #a6e3a1; font-weight: bold; border: 1px solid #45475a; border-radius: 4px; padding: 4px; }
            QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { background-color: #313244; width: 20px; }
            QTableWidget { background-color: #181825; color: #cdd6f4; gridline-color: #313244; border: 1px solid #313244; border-radius: 6px; selection-background-color: #45475a; }
            QHeaderView::section { background-color: #1e1e2e; color: #a6adc8; padding: 5px; border: 1px solid #313244; font-weight: bold; }
            QStatusBar { background-color: #11111b; color: #a6adc8; font-weight: bold; }
            QTabWidget::pane { border: 2px solid #313244; border-radius: 8px; background-color: #1e1e2e; }
            QTabBar::tab { background-color: #11111b; color: #585b70; padding: 10px 20px; font-weight: bold; font-size: 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 4px; border: 2px solid transparent; }
            QTabBar::tab:selected { background-color: #313244; color: #a6e3a1; border-top: 2px solid #a6e3a1; border-left: 2px solid #313244; border-right: 2px solid #313244; }
            QTabBar::tab:hover:!selected { background-color: #181825; color: #cdd6f4; }
            QMessageBox { background-color: #ffffff; /* 纯白背景 */border: 2px solid #d1d5db; /* 浅灰色精致边框 */}
            QMessageBox QLabel { color: #000000; /* 纯黑字体 */font-size: 14px; font-weight: bold; }
            QMessageBox QPushButton { background-color: #f3f4f6; /* 浅灰色按钮背景 */color: #000000; /* 按钮文字黑色 */border: 1px solid #d1d5db; /* 按钮加一个细边框增加质感 */border-radius: 6px; padding: 6px 20px; font-weight: bold;min-width: 60px; }
            QMessageBox QPushButton:hover { background-color: #e5e7eb; /* 鼠标悬停时稍微加深 */}
            QMessageBox QPushButton:pressed { background-color: #d1d5db; /* 按下时更深一点 */}
        """)

        self.thread = None 
        self.current_counts = {}
        self.current_video_path = ""
        
        # 💡 根据全局变量初始化物理标签 (1 ~ NUM_CHANNELS)
        self.labels = sorted(range(1, NUM_CHANNELS + 1), reverse=True)

        self.preview_frame = None       
        self.last_main_frame = None     

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 📺 左侧区域
        video_container = QVBoxLayout()
        self.video_label = QLabel("等待导入实验视频...\n(请从右侧面板选择视频文件)")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #11111b; color: #585b70; font-size: 20px; font-weight: bold; border: 2px dashed #45475a; border-radius: 12px;")
        self.video_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        video_container.addWidget(self.video_label)
        main_layout.addLayout(video_container, stretch=7)

        # 🗂️ 右侧标签页
        self.tabs = QTabWidget()
        
        # --- Tab 1: 🎮 工作台 ---
        tab_main = QWidget()
        layout_main = QVBoxLayout(tab_main)
        layout_main.setSpacing(12)

        control_group = QGroupBox("🚀 系统控制")
        control_layout = QVBoxLayout(control_group)
        self.btn_open = self.create_btn("📂 选择实验视频", "#89b4fa", "#11111b")
        self.btn_open.clicked.connect(self.open_video)
        self.btn_main_action = self.create_btn("▶ 请先导入视频", "#313244", "#a6adc8")
        self.btn_main_action.clicked.connect(self.handle_main_action)
        self.btn_main_action.setEnabled(False)
        
        control_layout.addWidget(self.btn_open)
        control_layout.addWidget(self.btn_main_action)
        layout_main.addWidget(control_group)

        data_group = QGroupBox("📊 实时数据")
        data_layout = QVBoxLayout(data_group)
        self.total_lcd = QLCDNumber()
        self.total_lcd.setDigitCount(5); self.total_lcd.setFixedHeight(60); self.total_lcd.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.total_lcd.setStyleSheet("color: #a6e3a1; background-color: #11111b; border: 2px solid #313244; border-radius: 8px;")
        
        # 表格初始化
        self.table = QTableWidget(len(self.labels), 2)
        self.table.setHorizontalHeaderLabels(["通道 ID", "计数"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False) 
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        data_layout.addWidget(QLabel("<center style='color:#a6adc8; font-size:11px;'>TOTAL WORM COUNT</center>"))
        data_layout.addWidget(self.total_lcd)
        data_layout.addWidget(QLabel("<center style='color:#a6adc8; font-size:11px;'>CHANNEL DISTRIBUTION</center>"))
        data_layout.addWidget(self.table)
        layout_main.addWidget(data_group, stretch=1)

        self.finish_group = QGroupBox("✅ 分析完成")
        self.finish_group.setStyleSheet("QGroupBox { border-color: #a6e3a1; color: #a6e3a1; }")
        finish_layout = QVBoxLayout(self.finish_group)
        self.btn_export = self.create_btn("📊 导出 Excel 报告", "#a6e3a1", "#11111b")
        self.btn_export.clicked.connect(self.export_results)
        finish_layout.addWidget(self.btn_export)
        self.finish_group.hide()
        layout_main.addWidget(self.finish_group)

        # --- Tab 2: ⚙️ 参数调节 (仅保留3项) ---
        tab_params = QWidget()
        layout_params = QVBoxLayout(tab_params)
        
        param_group = QGroupBox("⚙️ 核心参数 (实时生效)")
        param_layout = QFormLayout(param_group)
        param_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 1. 通道数量 (💡 新增)
        self.spin_channels = QSpinBox()
        self.spin_channels.setFixedHeight(40)
        self.spin_channels.setRange(1, 100)
        self.spin_channels.setValue(NUM_CHANNELS)
        self.spin_channels.valueChanged.connect(self.on_channels_changed)
        param_layout.addRow("微流控通道数量:", self.spin_channels)

        # 2. 检测线高度
        self.spin_tripwire = QDoubleSpinBox()
        self.spin_tripwire.setFixedHeight(40)
        self.spin_tripwire.setRange(0.1, 0.9); self.spin_tripwire.setSingleStep(0.02); self.spin_tripwire.setValue(TRIPWIRE_RATIO)
        self.spin_tripwire.valueChanged.connect(self.on_tripwire_changed) 
        param_layout.addRow("检测线高度 (红线):", self.spin_tripwire)

        # 3. 最小虫体面积
        self.spin_min_area = QSpinBox()
        self.spin_min_area.setFixedHeight(40)
        self.spin_min_area.setRange(5, 500); self.spin_min_area.setSingleStep(10); self.spin_min_area.setValue(MIN_AREA)
        self.spin_min_area.valueChanged.connect(lambda v: self.update_thread_param('min_area', v))
        param_layout.addRow("虫体滤噪 (最小面积):", self.spin_min_area)

        # 4. Mask 上界 (屏蔽上方噪点)
        self.spin_mask_top = QDoubleSpinBox()
        self.spin_mask_top.setFixedHeight(40)
        self.spin_mask_top.setRange(0.0, 1.0); self.spin_mask_top.setSingleStep(0.02); self.spin_mask_top.setValue(ROI_MASK_TOP_RATIO)
        self.spin_mask_top.valueChanged.connect(self.on_mask_changed)
        param_layout.addRow("Mask 上界 (屏蔽上方):", self.spin_mask_top)

        # 5. Mask 下界 (屏蔽下方噪点)
        self.spin_mask_bottom = QDoubleSpinBox()
        self.spin_mask_bottom.setFixedHeight(40)
        self.spin_mask_bottom.setRange(0.0, 1.0); self.spin_mask_bottom.setSingleStep(0.02); self.spin_mask_bottom.setValue(ROI_MASK_BOTTOM_RATIO)
        self.spin_mask_bottom.valueChanged.connect(self.on_mask_changed)
        param_layout.addRow("Mask 下界 (屏蔽下方):", self.spin_mask_bottom)

        layout_params.addWidget(param_group)
        
        tips_label = QLabel("💡 提示：在【暂停】或【未开始】时，\n修改高度可直接在画面预览检测线位置。\n更改通道数量将实时重置表格。")
        tips_label.setStyleSheet("color: #89b4fa; font-weight: normal; line-height: 1.5;")
        tips_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_params.addWidget(tips_label)
        layout_params.addStretch(1) 

        self.tabs.addTab(tab_main, "🎮 工作台")
        self.tabs.addTab(tab_params, "⚙️ 参数调节")
        
        main_layout.addWidget(self.tabs, stretch=3)

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("✅ 系统就绪，请先选择实验视频。")
        self.reset_ui()

    # ==========================================================
    # 核心交互逻辑
    # ==========================================================
    def create_btn(self, text, bg_color=None, text_color=None):
        btn = QPushButton(text)
        if bg_color and text_color:
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {bg_color}; color: {text_color}; }} 
                QPushButton:hover {{ filter: brightness(110%); border: 1px solid white; }}
                QPushButton:disabled {{ background-color: #181825; color: #585b70; border: 1px solid #313244; }}
            """)
        return btn

    def update_thread_param(self, key, value):
        if self.thread and self.thread.isRunning():
            self.thread.update_param(key, value)

    def on_channels_changed(self, value):
        """💡 当调整通道数量时触发"""
        self.update_thread_param('num_channels', value)
        
        # 重新生成标签列表 (例如 8 -> [8,7,6,5,4,3,2,1])
        self.labels = sorted(range(1, value + 1), reverse=True)
        
        # 动态重建表格结构，并尽可能保留已有计数
        new_counts = {label: self.current_counts.get(label, 0) for label in self.labels}
        self.current_counts = new_counts
        
        self.table.setRowCount(len(self.labels))
        for i, label in enumerate(self.labels):
            item_id = QTableWidgetItem(f"CH-{label:02d}")
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, item_id)
            
            item_count = QTableWidgetItem(str(self.current_counts[label]))
            item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, item_count)

    def on_tripwire_changed(self, value):
        self.update_thread_param('tripwire_ratio', value)
        if self.thread is None or not self.thread.isRunning() or self.thread.is_paused:
            self.render_preview_frame()

    def on_mask_changed(self, value):
        self.update_thread_param('mask_top_ratio', self.spin_mask_top.value())
        self.update_thread_param('mask_bottom_ratio', self.spin_mask_bottom.value())
        if self.thread is None or not self.thread.isRunning() or self.thread.is_paused:
            self.render_preview_frame()

    def render_preview_frame(self):
        img_to_draw = None
        if self.thread and self.thread.isRunning() and self.thread.is_paused:
            if self.last_main_frame is not None:
                img_to_draw = self.last_main_frame.copy()
        elif not (self.thread and self.thread.isRunning()):
            if self.preview_frame is not None:
                img_to_draw = self.preview_frame.copy()

        if img_to_draw is not None:
            h, w = img_to_draw.shape[:2]
            y = int(h * self.spin_tripwire.value())
            cv2.line(img_to_draw, (0, y), (w, y), (0, 0, 255), 3)
            cv2.putText(img_to_draw, f"Tripwire: {self.spin_tripwire.value():.2f}", 
                        (15, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            # Mask 上下界预览
            mask_top_y = int(h * self.spin_mask_top.value())
            mask_bot_y = int(h * self.spin_mask_bottom.value())
            cv2.line(img_to_draw, (0, mask_top_y), (w, mask_top_y), (0, 215, 255), 2)
            cv2.putText(img_to_draw, f"Mask Top: {self.spin_mask_top.value():.2f}",
                        (15, mask_top_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 1)
            cv2.line(img_to_draw, (0, mask_bot_y), (w, mask_bot_y), (0, 215, 255), 2)
            cv2.putText(img_to_draw, f"Mask Bot: {self.spin_mask_bottom.value():.2f}",
                        (15, mask_bot_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 1)
            fmt = QImage.Format.Format_RGB888 if len(img_to_draw.shape)==3 else QImage.Format.Format_Grayscale8
            qt_img = QImage(img_to_draw.data, w, h, img_to_draw.strides[0], fmt)
            if len(img_to_draw.shape)==3: qt_img = qt_img.rgbSwapped()
            pixmap = QPixmap.fromImage(qt_img).scaled(self.video_label.width(), self.video_label.height(), 
                                                      Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.video_label.setPixmap(pixmap)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self.btn_main_action.isEnabled():
            self.handle_main_action()
        super().keyPressEvent(event)

    def handle_main_action(self):
        if self.thread is None or not self.thread.isRunning():
            self.start_analysis()
        elif self.thread.isRunning() and not self.thread.is_paused:
            self.thread.toggle_pause()
            self.btn_main_action.setText("▶ 继续分析 (Space)")
            self.btn_main_action.setStyleSheet("background-color: #a6e3a1; color: #11111b;") 
            self.statusBar.showMessage("⏸ 分析已暂停，可切换到【参数调节】预览检测线。")
        elif self.thread.isRunning() and self.thread.is_paused:
            self.thread.toggle_pause()
            self.btn_main_action.setText("⏸ 暂停分析 (Space)")
            self.btn_main_action.setStyleSheet("background-color: #f9e2af; color: #11111b;") 
            self.statusBar.showMessage("▶️ 正在实时分析中...")
        
        self.setFocus() 

    def open_video(self):
        if self.thread and self.thread.isRunning():
            reply = QMessageBox.question(self, '中止确认', '当前正在分析视频，是否要强制中止并导入新视频？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No: return
            self.thread.stop()
            self.thread = None

        file_name, _ = QFileDialog.getOpenFileName(self, "选择实验视频", "", "视频 (*.mp4 *.avi *.mov *.mkv)")
        if file_name:
            self.current_video_path = file_name
            self.reset_ui()
            self.finish_group.hide()
            
            self.btn_main_action.setEnabled(True)
            self.btn_main_action.setText("▶ 开始识别")
            self.btn_main_action.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
            
            self.statusBar.showMessage(f"📂 已加载: {os.path.basename(file_name)}。你可以切换到【参数调节】预览检测线高度。")
            
            cap = cv2.VideoCapture(file_name)
            ret, frame = cap.read()
            if ret:
                self.preview_frame = frame.copy()
                self.render_preview_frame()
            else:
                self.video_label.setText("成功导入，但预览画面失败\n请直接点击【开始识别】")
            cap.release()

    def start_analysis(self):
        if not self.current_video_path: return
        self.reset_ui()
        self.finish_group.hide()
        
        self.btn_main_action.setText("⏸ 暂停分析 (Space)")
        self.btn_main_action.setStyleSheet("background-color: #f9e2af; color: #11111b;") 
        
        self.thread = VideoThread(self.current_video_path)
        # 传递最新的 3 个参数给线程
        self.thread.update_param('num_channels', self.spin_channels.value())
        self.thread.update_param('tripwire_ratio', self.spin_tripwire.value())
        self.thread.update_param('min_area', self.spin_min_area.value())
        self.thread.update_param('mask_top_ratio', self.spin_mask_top.value())
        self.thread.update_param('mask_bottom_ratio', self.spin_mask_bottom.value())

        self.thread.change_pixmap_signal.connect(self.update_frame)
        self.thread.update_counts_signal.connect(self.update_stats)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()
        
        self.tabs.setCurrentIndex(0) 
        self.statusBar.showMessage("▶️ 正在实时分析中...")
        self.setFocus()

    def on_finished(self):
        self.btn_main_action.setEnabled(True)
        self.btn_main_action.setText("🔄 重新分析该视频")
        self.btn_main_action.setStyleSheet("background-color: #89b4fa; color: #11111b;") 
        self.finish_group.show()
        self.tabs.setCurrentIndex(0) 
        self.statusBar.showMessage("✅ 视频分析完毕，您可以导出报告或重新分析。")

    def export_results(self):
        if not self.current_counts: return
        base_name = os.path.splitext(os.path.basename(self.current_video_path))[0]
        save_path, _ = QFileDialog.getSaveFileName(self, "保存 Excel 报告", f"{base_name}_分析报告.xlsx", "Excel Files (*.xlsx)")
        if save_path:
            try:
                data = { "微通道编号": [f"CH-{label:02d}" for label in sorted(self.current_counts.keys())], "线虫统计数量": [self.current_counts[label] for label in sorted(self.current_counts.keys())] }
                df = pd.DataFrame(data)
                df = pd.concat([df, pd.DataFrame({"微通道编号": ["总计 (Total)"], "线虫统计数量": [sum(self.current_counts.values())]})], ignore_index=True)
                with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='计数结果')
                    pd.DataFrame({"项目": ["分析文件", "分析时间"], "内容": [os.path.basename(self.current_video_path), pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')]}).to_excel(writer, index=False, sheet_name='实验信息')
                self.statusBar.showMessage(f"💾 报告已成功导出至: {save_path}")
                QMessageBox.information(self, "导出成功", "Excel 报表已生成！")
            except Exception as e: QMessageBox.critical(self, "导出失败", str(e))

    def reset_ui(self):
        self.total_lcd.display(0)
        self.current_counts = {label: 0 for label in self.labels}
        self.table.setRowCount(len(self.labels)) # 确保表格行数正确
        for i, label in enumerate(self.labels):
            item_id = QTableWidgetItem(f"CH-{label:02d}"); item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setItem(i, 0, item_id)
            item_count = QTableWidgetItem("0"); item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setItem(i, 1, item_count)

    def update_frame(self, main_frame, mask_frame):
        self.last_main_frame = main_frame.copy() 
        frame = main_frame 
        h, w = frame.shape[:2]
        fmt = QImage.Format.Format_RGB888 if len(frame.shape)==3 else QImage.Format.Format_Grayscale8
        qt_img = QImage(frame.data, w, h, frame.strides[0], fmt)
        if len(frame.shape)==3: qt_img = qt_img.rgbSwapped()
        self.video_label.setPixmap(QPixmap.fromImage(qt_img).scaled(self.video_label.width(), self.video_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def update_stats(self, counts):
        self.current_counts = counts
        self.total_lcd.display(sum(counts.values()))
        for i, label in enumerate(self.labels):
            val = str(counts.get(label, 0)); item = self.table.item(i, 1)
            if item and item.text() != val: item.setText(val); item.setForeground(QColor("#a6e3a1"))

    def closeEvent(self, event):
        if self.thread: self.thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WormCounterApp()
    window.show()
    sys.exit(app.exec())
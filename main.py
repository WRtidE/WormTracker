import sys
import cv2
import numpy as np
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, 
                             QVBoxLayout, QHBoxLayout, QLCDNumber, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QSizePolicy, 
                             QPushButton, QFileDialog, QMessageBox)
from PyQt6.QtGui import QImage, QPixmap, QColor, QFont
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# ==========================================================
# 🟢 从 v4.py 导入算法核心
# ==========================================================
from v4 import (
    get_interpolated_grid, detect_worms, update_tracks, count_crossings, draw_dashboard,
    NUM_CHANNELS, X_MARGIN, WALL_RATIO, TRIPWIRE_RATIO, MIN_AREA, 
    BG_HISTORY, INIT_FRAME_INDEX, PANIC_NOISE_RATIO, GRID_MUTATION_TOLERANCE, 
    COOLDOWN_FRAMES, PHYSICAL_LABELS
)

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray, np.ndarray)
    update_counts_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal() # 💡 新增：播放完成信号

    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path  
        self.is_running = True        
        self.is_paused = False        

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened(): return

        backSub = cv2.createBackgroundSubtractorMOG2(history=BG_HISTORY, varThreshold=16, detectShadows=False)
        counts = {label: 0 for label in PHYSICAL_LABELS}
        active_worms, cross_cooldown = {}, {}
        next_worm_id, frame_idx = 0, 0
        base_channel_width, grid_data, tripwire_y, panic_cooldown = None, None, 0, 0

        while cap.isOpened() and self.is_running:
            if self.is_paused:
                self.msleep(50) 
                continue

            ret, frame = cap.read()
            if not ret: break # 💡 视频自然结束
            frame_idx += 1
            is_panic_now = False

            # --- 算法逻辑 (完全调用 v4) ---
            try:
                grid_data = get_interpolated_grid(frame, NUM_CHANNELS, X_MARGIN, wall_ratio=WALL_RATIO)
                if base_channel_width is None and frame_idx >= INIT_FRAME_INDEX:
                    base_channel_width = grid_data['channel_width']
                if base_channel_width is not None:
                    mutation = abs(grid_data['channel_width'] - base_channel_width) / base_channel_width
                    if mutation > GRID_MUTATION_TOLERANCE: is_panic_now = True
                tripwire_y = int(frame.shape[0] * TRIPWIRE_RATIO)
            except Exception: is_panic_now = True

            if frame_idx > INIT_FRAME_INDEX:
                centroids, fg_mask, noise_ratio, raw_fg = detect_worms(frame, backSub, grid_data, MIN_AREA)
                if noise_ratio > PANIC_NOISE_RATIO: is_panic_now = True
            else: raw_fg = None
                
            if is_panic_now: panic_cooldown = COOLDOWN_FRAMES

            if panic_cooldown > 0:
                panic_cooldown -= 1
                active_worms.clear(); cross_cooldown.clear()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                backSub.apply(blur, learningRate=0.1) 
                display_frame = draw_dashboard(frame, counts, grid_data, {}, tripwire_y, None, is_panic=True, cooldown_rem=panic_cooldown)
            elif frame_idx > INIT_FRAME_INDEX:
                active_worms, next_worm_id, movements, cross_cooldown = update_tracks(centroids, active_worms, next_worm_id, cross_cooldown)
                counts, cross_cooldown = count_crossings(active_worms, counts, grid_data['channel_bounds'], tripwire_y, cross_cooldown)
                display_frame = draw_dashboard(frame, counts, grid_data, active_worms, tripwire_y, None)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                backSub.apply(blur, learningRate=0.05)
                display_frame = draw_dashboard(frame, counts, grid_data, {}, tripwire_y, None)

            mask_frame = raw_fg if raw_fg is not None else np.zeros(frame.shape[:2], dtype=np.uint8)
            self.change_pixmap_signal.emit(display_frame.copy(), mask_frame.copy())
            self.update_counts_signal.emit(counts)
            QThread.msleep(1)

        cap.release()
        if self.is_running: # 💡 如果不是被手动停止的，则发送完成信号
            self.finished_signal.emit()

    def toggle_pause(self): self.is_paused = not self.is_paused
    def stop(self): self.is_running = False; self.wait()


class WormCounterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WormTrack Pro - 自动化线虫计数系统")
        self.setMinimumSize(1100, 800)
        self.setStyleSheet("QMainWindow { background-color: #1a1a1a; }")

        self.thread = None 
        self.view_mode = "normal" 
        self.current_counts = {}
        self.current_video_path = ""

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # --- 左侧视频 ---
        video_container = QVBoxLayout()
        self.video_label = QLabel("等待导入实验视频...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: #555; font-size: 18px; border: 2px dashed #333; border-radius: 10px;")
        self.video_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        video_container.addWidget(self.video_label)
        main_layout.addLayout(video_container, stretch=7)

        # --- 右侧面板 ---
        side_panel = QVBoxLayout()
        
        # 功能控制组
        self.btn_open = self.create_btn("📂 导入视频", "#2196F3", self.open_video)
        side_panel.addWidget(self.btn_open)

        self.btn_pause = self.create_btn("⏸ 暂停分析 (Space)", "#555", self.toggle_video_pause)
        self.btn_pause.setEnabled(False)
        side_panel.addWidget(self.btn_pause)

        self.btn_view = self.create_btn("👁️ 视图: 正常画面", "#4CAF50", self.toggle_view)
        side_panel.addWidget(self.btn_view)

        # 💡 完成后显示的特殊按钮组
        self.finish_controls = QWidget()
        finish_layout = QVBoxLayout(self.finish_controls)
        finish_layout.setContentsMargins(0, 10, 0, 0)
        
        self.btn_replay = self.create_btn("🔄 重新播放", "#249B26", self.replay_video)
        self.btn_print = self.create_btn("🖨️ 打印/导出结果 (.txt)", "#E91E63", self.export_results)
        finish_layout.addWidget(self.btn_replay)
        finish_layout.addWidget(self.btn_print)
        
        self.finish_controls.hide() # 💡 默认隐藏
        side_panel.addWidget(self.finish_controls)

        # 数据显示
        side_panel.addWidget(QLabel("<span style='color:#777; font-weight:bold;'>TOTAL COUNT</span>"))
        self.total_lcd = QLCDNumber()
        self.total_lcd.setDigitCount(5); self.total_lcd.setFixedHeight(70)
        self.total_lcd.setStyleSheet("color: #00FF7F; background: #111; border: 1px solid #333;")
        side_panel.addWidget(self.total_lcd)

        side_panel.addWidget(QLabel("<span style='color:#777; font-weight:bold;'>DISTRIBUTION</span>"))
        self.table = QTableWidget(len(PHYSICAL_LABELS), 2)
        self.table.setHorizontalHeaderLabels(["ID", "Count"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("QTableWidget { background-color: #111; color: white; border: none; }")
        side_panel.addWidget(self.table)
        
        main_layout.addLayout(side_panel, stretch=3)
        self.labels = sorted(PHYSICAL_LABELS, reverse=True)
        self.reset_ui()

    def create_btn(self, text, color, func):
        btn = QPushButton(text)
        btn.setFixedHeight(40)
        btn.setStyleSheet(f"QPushButton {{ background-color: {color}; color: white; font-weight: bold; border-radius: 4px; }}")
        btn.clicked.connect(func)
        return btn

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self.btn_pause.isEnabled():
            self.toggle_video_pause()
        super().keyPressEvent(event)

    def open_video(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "选择视频", "", "视频 (*.mp4 *.avi *.mov *.mkv)")
        if file_name:
            self.current_video_path = file_name
            self.start_analysis(file_name)

    def start_analysis(self, path):
        if self.thread and self.thread.isRunning(): self.thread.stop()
        self.reset_ui()
        self.finish_controls.hide()
        self.thread = VideoThread(path)
        self.thread.change_pixmap_signal.connect(self.update_frame)
        self.thread.update_counts_signal.connect(self.update_stats)
        self.thread.finished_signal.connect(self.on_finished) # 💡 连接完成信号
        self.thread.start()
        
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("⏸ 暂停分析 (Space)")
        self.btn_open.setText("⏹ 重新导入")
        self.setFocus()

    def on_finished(self):
        """💡 视频播放完成后触发"""
        self.btn_pause.setEnabled(False)
        self.finish_controls.show() # 💡 显示重播和打印按钮
        QMessageBox.information(self, "分析完成", "实验视频处理完毕，您可以打印结果或重新播放。")

    def replay_video(self):
        if self.current_video_path:
            self.start_analysis(self.current_video_path)

    def export_results(self):
        """💡 导出 TXT 文件"""
        if not self.current_counts: return
        
        # 默认保存名称：视频名_results.txt
        base_name = os.path.splitext(os.path.basename(self.current_video_path))[0]
        save_path, _ = QFileDialog.getSaveFileName(self, "保存结果", f"{base_name}_results.txt", "Text Files (*.txt)")
        
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write("="*40 + "\n")
                    f.write("      WormTrack Pro 实验分析报告\n")
                    f.write("="*40 + "\n")
                    f.write(f"视频文件: {self.current_video_path}\n")
                    f.write(f"总计线虫: {sum(self.current_counts.values())} 条\n")
                    f.write("-" * 40 + "\n")
                    f.write(f"{'通道编号':<10} | {'线虫数量':<10}\n")
                    f.write("-" * 40 + "\n")
                    for label in sorted(self.current_counts.keys()):
                        f.write(f"CH-{label:02d}      | {self.current_counts[label]:<10}\n")
                    f.write("-" * 40 + "\n")
                    f.write("报告生成时间: 自动生成\n")
                QMessageBox.information(self, "导出成功", f"结果已保存至:\n{save_path}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"错误原因: {str(e)}")

    def toggle_video_pause(self):
        if self.thread:
            self.thread.toggle_pause()
            is_paused = self.thread.is_paused
            self.btn_pause.setText("▶ 继续分析" if is_paused else "⏸ 暂停分析")
            self.btn_pause.setStyleSheet(f"QPushButton {{ background-color: {'#FF9800' if is_paused else '#2196F3'}; color: white; font-weight: bold; }}")
        self.setFocus()

    def toggle_view(self):
        self.view_mode = "mask" if self.view_mode == "normal" else "normal"
        self.btn_view.setText(f"👁️ 视图: {'算法遮罩' if self.view_mode == 'mask' else '正常画面'}")
        self.btn_view.setStyleSheet(f"QPushButton {{ background-color: {'#9C27B0' if self.view_mode == 'mask' else '#4CAF50'}; color: white; font-weight: bold; }}")
        self.setFocus()

    def reset_ui(self):
        self.total_lcd.display(0)
        self.current_counts = {label: 0 for label in self.labels}
        for i, label in enumerate(self.labels):
            self.table.setItem(i, 0, QTableWidgetItem(f"CH-{label:02d}"))
            self.table.setItem(i, 1, QTableWidgetItem("0"))

    def update_frame(self, main_frame, mask_frame):
        frame = main_frame if self.view_mode == "normal" else mask_frame
        h, w = frame.shape[:2]
        fmt = QImage.Format.Format_RGB888 if len(frame.shape)==3 else QImage.Format.Format_Grayscale8
        qt_img = QImage(frame.data, w, h, frame.strides[0], fmt)
        if len(frame.shape)==3: qt_img = qt_img.rgbSwapped()
        self.video_label.setPixmap(QPixmap.fromImage(qt_img).scaled(self.video_label.width(), self.video_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def update_stats(self, counts):
        self.current_counts = counts
        self.total_lcd.display(sum(counts.values()))
        for i, label in enumerate(self.labels):
            val = str(counts.get(label, 0))
            item = self.table.item(i, 1)
            if item and item.text() != val:
                item.setText(val); item.setForeground(QColor("#00FF7F"))

    def closeEvent(self, event):
        if self.thread: self.thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); window = WormCounterApp(); window.show(); sys.exit(app.exec())
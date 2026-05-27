"""视频处理线程

封装视频读取、引擎调用、UI 信号发射的完整流水线。
支持暂停、参数热调、熔断冷却。
"""

from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from wormtracker.engine.base import BaseEngine
from wormtracker.core.grid import get_interpolated_grid
from wormtracker.core.visualize import draw_dashboard
from wormtracker.config import WormTrackerConfig, get_config


class VideoThread(QThread):
    """视频分析工作线程"""

    # 信号
    change_pixmap_signal = pyqtSignal(np.ndarray, np.ndarray)
    update_counts_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()

    def __init__(
        self,
        video_path: str,
        engine: BaseEngine,
        config: Optional[WormTrackerConfig] = None,
    ):
        super().__init__()
        self.video_path = video_path
        self.engine = engine
        self.config = config or get_config()

        self.is_running = True
        self.is_paused = False
        self._seek_target: int = -1

        # 可动态调参的字段
        self._dynamic_params: dict = {
            "num_channels": self.config.num_channels,
            "tripwire_ratio": self.config.tripwire_ratio,
            "min_area": self.config.min_area,
            "mask_top_ratio": self.config.mask_top_ratio,
            "mask_bottom_ratio": self.config.mask_bottom_ratio,
            "wall_peak_half_width": self.config.wall_peak_half_width,
        }

    def update_param(self, key: str, value) -> None:
        self._dynamic_params[key] = value

    def run(self) -> None:
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            self.finished_signal.emit()
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # 初始化计数器
        n_channels = self._dynamic_params["num_channels"]
        counts = {label: 0 for label in range(1, n_channels + 1)}
        cross_cooldown: dict = {}

        frame_idx = 0
        base_channel_width = None
        panic_cooldown = 0

        while cap.isOpened() and self.is_running:
            # ---- 处理跳转请求 ----
            if self._seek_target >= 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, self._seek_target)
                frame_idx = self._seek_target
                self._seek_target = -1
                # 重置引擎状态，避免跳转后状态错乱
                self.engine.reset()
                cross_cooldown.clear()
                counts = {label: 0 for label in counts}
                base_channel_width = None
                panic_cooldown = 0
                self.progress_signal.emit(frame_idx, total_frames)
                self.update_counts_signal.emit(counts)

            if self.is_paused:
                QThread.msleep(50)
                continue

            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            self.progress_signal.emit(frame_idx, total_frames)
            is_panic_now = False

            # ---- 动态同步通道数量 ----
            current_channels = self._dynamic_params["num_channels"]
            for i in range(1, current_channels + 1):
                if i not in counts:
                    counts[i] = 0

            # ---- 1. 网格计算 & 熔断探针 ----
            try:
                self.config.wall_peak_half_width = self._dynamic_params["wall_peak_half_width"]
                grid_data = get_interpolated_grid(
                    frame,
                    current_channels,
                    (self.config.x_margin_left, self.config.x_margin_right),
                    wall_ratio=self.config.wall_ratio,
                    refine_walls=self.config.wall_refine,
                    wall_peak_half_width=self.config.wall_peak_half_width,
                )

                if (
                    base_channel_width is None
                    and frame_idx >= self.config.init_frame_index
                ):
                    base_channel_width = grid_data["channel_width"]

                if base_channel_width is not None:
                    mutation = (
                        abs(grid_data["channel_width"] - base_channel_width)
                        / base_channel_width
                    )
                    if mutation > self.config.grid_mutation_tolerance:
                        is_panic_now = True
            except Exception:
                is_panic_now = True
                continue

            tripwire_y = int(frame.shape[0] * self._dynamic_params["tripwire_ratio"])
            mask_top_y = int(frame.shape[0] * self._dynamic_params["mask_top_ratio"])
            mask_bottom_y = int(frame.shape[0] * self._dynamic_params["mask_bottom_ratio"])

            # ---- 2. 引擎处理 ----
            raw_fg = None
            active_worms = {}
            crossing_channels = frozenset()

            if frame_idx <= self.config.init_frame_index:
                self.engine.warmup(frame)
            else:
                # 将动态参数同步到 config 中供引擎使用
                self.config.num_channels = current_channels
                self.config.tripwire_ratio = self._dynamic_params["tripwire_ratio"]
                self.config.min_area = self._dynamic_params["min_area"]
                self.config.mask_top_ratio = self._dynamic_params["mask_top_ratio"]
                self.config.mask_bottom_ratio = self._dynamic_params["mask_bottom_ratio"]
                self.config.wall_peak_half_width = self._dynamic_params["wall_peak_half_width"]

                result = self.engine.process_frame(
                    frame, frame_idx, grid_data, counts, cross_cooldown
                )
                active_worms = result.active_worms
                raw_fg = result.raw_fg
                crossing_channels = result.crossing_channels
                if result.is_panic:
                    is_panic_now = True

            # ---- 3. 熔断状态机 ----
            if is_panic_now:
                panic_cooldown = self.config.cooldown_frames

            if panic_cooldown > 0:
                panic_cooldown -= 1
                self.engine.reset()
                cross_cooldown.clear()
                # 强制高学习率背景吸收 (MOG2 需要)
                self.engine.warmup(frame)
                display_frame = draw_dashboard(
                    frame, counts, grid_data, {}, tripwire_y,
                    raw_fg,
                    is_panic=True, cooldown_rem=panic_cooldown,
                    mask_top=mask_top_y, mask_bottom=mask_bottom_y,
                )
            elif frame_idx > self.config.init_frame_index:
                display_frame = draw_dashboard(
                    frame, counts, grid_data,
                    active_worms, tripwire_y,
                    raw_fg,
                    mask_top=mask_top_y, mask_bottom=mask_bottom_y,
                    crossing_channels=crossing_channels,
                )
            else:
                display_frame = draw_dashboard(
                    frame, counts, grid_data, {}, tripwire_y,
                    raw_fg,
                    mask_top=mask_top_y, mask_bottom=mask_bottom_y,
                )
                cv2.putText(
                    display_frame, "WARMING UP...",
                    (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2,
                )

            # ---- 4. 信号发射 ----
            mask_frame = (
                raw_fg if raw_fg is not None
                else np.zeros(frame.shape[:2], dtype=np.uint8)
            )
            # 注：raw_fg 已在 MOG2._detect 中完成了墙壁遮罩 + Y轴遮罩，
            # 此处无需重复处理，直接传给 UI 的识别视角即可。
            self.change_pixmap_signal.emit(display_frame.copy(), mask_frame.copy())
            self.update_counts_signal.emit(counts)

            QThread.msleep(1)

        cap.release()
        if self.is_running:
            self.finished_signal.emit()

    def toggle_pause(self) -> None:
        self.is_paused = not self.is_paused

    def seek_frame(self, frame_idx: int) -> None:
        """跳转到指定帧 (仅在暂停时可用，通过外部 cap 引用实现)

        注意：OpenCV 的 seek 精度有限，实际位置可能偏差 1-2 帧。
        跳转后会重置引擎状态以避免状态错乱。
        """
        self._seek_target = frame_idx

    def stop(self) -> None:
        self.is_running = False
        self.wait()

from __future__ import annotations

import hashlib
import queue
import threading
from pathlib import Path
from typing import Optional, Tuple

from tkinter import filedialog, messagebox

from .water_core import RasterData
from .water_dem import DemCacheCancelled, build_dem_cache, read_dem_metadata, save_dem_cache


class DemWorkflowMixin:
    def _init_dem_state(self) -> None:
        self.dem_path: Optional[Path] = None
        self.dem_cache_arrays = None
        self.dem_cache_metadata = None
        self.dem_cache_data_path: Optional[Path] = None
        self.dem_cache_meta_path: Optional[Path] = None
        self._dem_cache_thread: Optional[threading.Thread] = None
        self._dem_cache_cancel = threading.Event()
        self._dem_cache_queue: "queue.Queue[Tuple[object, ...]]" = queue.Queue()
        self._dem_cache_poll_job: Optional[str] = None
        self._dem_cache_task_id = 0

    def _clear_dem_state(self) -> None:
        self.cancel_dem_cache_task(silent=True)
        self._dem_cache_task_id += 1
        self.dem_path = None
        self.dem_cache_arrays = None
        self.dem_cache_metadata = None
        self.dem_cache_data_path = None
        self.dem_cache_meta_path = None
        if hasattr(self, "dem_file_var"):
            self.dem_file_var.set("未加载")
        if hasattr(self, "dem_cache_status_var"):
            self.dem_cache_status_var.set("未生成")
        self._refresh_dem_controls()

    def load_dem_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="选择DEM文件",
            initialdir=str(self.workspace_dir),
            filetypes=[("DEM GeoTIFF", "*.tif *.tiff"), ("All files", "*.*")],
        )
        if path:
            self.load_dem(Path(path))

    def load_dem(self, path: Path, update_autosave: bool = True) -> None:
        try:
            meta = read_dem_metadata(path)
        except Exception as exc:
            messagebox.showerror("DEM加载失败", str(exc))
            return
        self.dem_path = path
        self.dem_cache_arrays = None
        self.dem_cache_metadata = None
        self.dem_cache_data_path = None
        self.dem_cache_meta_path = None
        self.dem_file_var.set(
            f"{self._store_path(path)} | {meta.width}x{meta.height} | {meta.crs_text or '无CRS'} | {meta.resolution[0]:.3g}x{meta.resolution[1]:.3g}"
        )
        self.dem_cache_status_var.set("已加载DEM，尚未生成缓存")
        self.info_var.set(f"已加载DEM {path.name}")
        self._refresh_dem_controls()
        self.update_mode_status()
        if update_autosave and self.autosave_var.get():
            self.save_autosave()

    def start_locked_dem_cache_task(self) -> None:
        if self._dem_cache_is_running():
            messagebox.showinfo("提示", "DEM缓存任务正在运行。")
            return
        if self.dem_path is None:
            messagebox.showwarning("提示", "请先加载DEM文件。")
            return
        if self.flow_raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        locked_cells = self._locked_flow_cells_set()
        if not locked_cells:
            messagebox.showwarning("提示", "请先在流向辅助中锁定需要处理的河道。")
            return
        row_range, col_range = self._dem_cache_range_for_locked_cells(self.flow_raster, locked_cells)
        coarse_cells = (row_range[1] - row_range[0]) * (col_range[1] - col_range[0])
        if coarse_cells <= 0:
            messagebox.showwarning("提示", "锁定范围无有效栅格。")
            return
        if coarse_cells > 100_000 and not messagebox.askyesno(
            "确认生成DEM缓存",
            f"当前局部范围包含 {coarse_cells} 个ASC/FDR粗像元，可能耗时较长。\n是否继续生成？",
        ):
            return
        raster_snapshot = self.flow_raster.copy()
        cache_data_path, cache_meta_path = self._dem_cache_paths(self.dem_path, raster_snapshot, row_range, col_range)
        self._dem_cache_cancel.clear()
        self._dem_cache_task_id += 1
        task_id = self._dem_cache_task_id
        self.dem_cache_status_var.set(f"准备生成缓存：{coarse_cells} 个粗像元")
        self.info_var.set("DEM缓存任务已启动，界面可继续浏览；需要停止时点击“取消缓存”。")
        self._refresh_dem_controls()
        thread = threading.Thread(
            target=self._run_dem_cache_task,
            args=(task_id, self.dem_path, raster_snapshot, row_range, col_range, cache_data_path, cache_meta_path),
            daemon=True,
        )
        self._dem_cache_thread = thread
        thread.start()
        self._refresh_dem_controls()
        self._schedule_dem_cache_poll()

    def cancel_dem_cache_task(self, silent: bool = False) -> None:
        if self._dem_cache_is_running():
            self._dem_cache_cancel.set()
            if not silent:
                self.dem_cache_status_var.set("正在取消DEM缓存任务...")
                self.info_var.set("正在取消DEM缓存任务，请稍候。")
        elif not silent and hasattr(self, "dem_cache_status_var"):
            self.dem_cache_status_var.set("当前没有正在运行的DEM缓存任务")
        self._refresh_dem_controls()

    def _run_dem_cache_task(
        self,
        task_id: int,
        dem_path: Path,
        raster: RasterData,
        row_range: Tuple[int, int],
        col_range: Tuple[int, int],
        cache_data_path: Path,
        cache_meta_path: Path,
    ) -> None:
        try:
            result = build_dem_cache(
                dem_path,
                raster,
                row_range=row_range,
                col_range=col_range,
                progress_callback=lambda done, total, readable, blocked: self._dem_cache_queue.put((task_id, "progress", done, total, readable, blocked)),
                cancel_checker=self._dem_cache_cancel.is_set,
                progress_interval_cells=50,
            )
            save_dem_cache(cache_data_path, cache_meta_path, result)
            self._dem_cache_queue.put((task_id, "done", result, cache_data_path, cache_meta_path))
        except DemCacheCancelled as exc:
            self._dem_cache_queue.put((task_id, "cancelled", str(exc)))
        except Exception as exc:
            self._dem_cache_queue.put((task_id, "error", str(exc)))

    def _schedule_dem_cache_poll(self) -> None:
        if self._dem_cache_poll_job is None:
            self._dem_cache_poll_job = self.after(120, self._poll_dem_cache_queue)

    def _poll_dem_cache_queue(self) -> None:
        self._dem_cache_poll_job = None
        keep_polling = self._dem_cache_is_running()
        while True:
            try:
                message = self._dem_cache_queue.get_nowait()
            except queue.Empty:
                break
            task_id = int(message[0])
            if task_id != self._dem_cache_task_id:
                continue
            kind = str(message[1])
            if kind == "progress":
                _, _, done, total, readable, blocked = message
                percent = 0.0 if int(total) <= 0 else int(done) * 100.0 / int(total)
                self.dem_cache_status_var.set(
                    f"生成中 {int(done)}/{int(total)} ({percent:.1f}%)，可读 {int(readable)}，跳过 {int(blocked)}"
                )
            elif kind == "done":
                _, _, result, data_path, meta_path = message
                self.dem_cache_arrays = result.arrays
                self.dem_cache_metadata = result.metadata
                self.dem_cache_data_path = Path(data_path)
                self.dem_cache_meta_path = Path(meta_path)
                stats = result.metadata.get("stats", {})
                self.dem_cache_status_var.set(
                    f"缓存完成：{stats.get('readable_cells', result.readable_cells)}/{stats.get('processed_cells', result.processed_cells)} 可读，{Path(data_path).name}"
                )
                self.info_var.set(f"DEM缓存已生成：{Path(data_path).name}")
                keep_polling = False
            elif kind == "cancelled":
                self.dem_cache_status_var.set("DEM缓存任务已取消")
                self.info_var.set("DEM缓存任务已取消，未保存半成品缓存。")
                keep_polling = False
            elif kind == "error":
                self.dem_cache_status_var.set(f"DEM缓存失败：{message[2]}")
                messagebox.showerror("DEM缓存失败", str(message[2]))
                keep_polling = False
        if keep_polling:
            self._schedule_dem_cache_poll()
        else:
            self._dem_cache_thread = None
            self._refresh_dem_controls()
            self.update_mode_status()

    def _dem_cache_is_running(self) -> bool:
        return self._dem_cache_thread is not None and self._dem_cache_thread.is_alive()

    def _refresh_dem_controls(self) -> None:
        if not hasattr(self, "btn_load_dem"):
            return
        running = self._dem_cache_is_running()
        has_dem = self.dem_path is not None
        has_locked = bool(self._locked_flow_cells_set()) if hasattr(self, "confirmed_flow_segment_cells") else False
        self.btn_load_dem.configure(state="disabled" if running else "normal")
        self.btn_build_dem_cache.configure(state="normal" if has_dem and has_locked and not running else "disabled")
        self.btn_cancel_dem_cache.configure(state="normal" if running else "disabled")

    def _dem_cache_range_for_locked_cells(self, raster: RasterData, locked_cells) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        rows = [row for row, _col in locked_cells]
        cols = [col for _row, col in locked_cells]
        buffer_cells = max(2, int(self.confluence_outer_radius_var.get()) + 1)
        row0 = max(0, min(rows) - buffer_cells)
        row1 = min(raster.nrows, max(rows) + buffer_cells + 1)
        col0 = max(0, min(cols) - buffer_cells)
        col1 = min(raster.ncols, max(cols) + buffer_cells + 1)
        return (row0, row1), (col0, col1)

    def _dem_cache_paths(
        self,
        dem_path: Path,
        raster: RasterData,
        row_range: Tuple[int, int],
        col_range: Tuple[int, int],
    ) -> Tuple[Path, Path]:
        cache_dir = self.user_data_dir / "dem_cache"
        try:
            stat = dem_path.stat()
            dem_key = f"{dem_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        except Exception:
            dem_key = str(dem_path)
        raster_key = (
            f"{raster.path}|{raster.nrows}|{raster.ncols}|{raster.header.xllcorner}|"
            f"{raster.header.yllcorner}|{raster.header.cellsize}|{raster.header.nodata}"
        )
        raw_key = f"{dem_key}|{raster_key}|{row_range}|{col_range}"
        digest = hashlib.sha1(raw_key.encode("utf-8", errors="ignore")).hexdigest()[:16]
        base_name = f"dem_cache_{digest}_r{row_range[0]}-{row_range[1]}_c{col_range[0]}-{col_range[1]}"
        return cache_dir / f"{base_name}.npz", cache_dir / f"{base_name}.json"

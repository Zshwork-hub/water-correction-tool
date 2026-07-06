from __future__ import annotations

import csv
import hashlib
import queue
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

from tkinter import filedialog, messagebox

from .water_core import RasterData
from .water_dem import (
    DemCacheCancelled,
    build_dem_cache,
    read_dem_metadata,
    save_dem_cache,
    score_flow_directions_from_cache,
    summarize_dem_direction_scores,
)


class DemWorkflowMixin:
    def _init_dem_state(self) -> None:
        self.dem_path: Optional[Path] = None
        self.dem_cache_arrays = None
        self.dem_cache_metadata = None
        self.dem_cache_data_path: Optional[Path] = None
        self.dem_cache_meta_path: Optional[Path] = None
        self.dem_score_status_text = "未评估"
        self._dem_conflict_cursor = -1
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
        if hasattr(self, "dem_score_status_var"):
            self.dem_score_status_var.set("未评估")
        self._dem_conflict_cursor = -1
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
        self.dem_score_status_var.set("未评估")
        self._dem_conflict_cursor = -1
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
                if self.flow_preview_state.has_preview():
                    self.update_dem_preview_coverage_hint()
                else:
                    self.dem_score_status_var.set("缓存已就绪，可评估当前流向预览")
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
        has_cache = self.dem_cache_arrays is not None and self.dem_cache_metadata is not None
        has_preview = self.flow_preview_state.has_preview() if hasattr(self, "flow_preview_state") else False
        has_scores = bool(getattr(self.flow_preview_state, "dem_score_details", [])) if hasattr(self, "flow_preview_state") else False
        has_conflicts = bool(self._dem_conflict_scores()) if has_scores else False
        self.btn_load_dem.configure(state="disabled" if running else "normal")
        self.btn_build_dem_cache.configure(state="normal" if has_dem and has_locked and not running else "disabled")
        self.btn_evaluate_dem_preview.configure(state="normal" if has_cache and has_preview and not running else "disabled")
        self.btn_locate_dem_conflict.configure(state="normal" if has_conflicts and not running else "disabled")
        self.btn_export_dem_report.configure(state="normal" if has_scores and not running else "disabled")
        self.btn_export_dem_conflicts.configure(state="normal" if has_conflicts and not running else "disabled")
        self.btn_cancel_dem_cache.configure(state="normal" if running else "disabled")

    def evaluate_current_flow_preview_with_dem(self) -> None:
        preview = self.flow_preview_state
        if not preview.has_preview():
            messagebox.showwarning("提示", "请先生成河道流向或周边汇流预览。")
            return
        if self.dem_cache_arrays is None or self.dem_cache_metadata is None:
            messagebox.showwarning("提示", "请先生成当前锁定范围的DEM缓存。")
            return
        all_ops = list(preview.ops) + list(preview.unchanged_ops)
        if not all_ops:
            messagebox.showwarning("提示", "当前预览没有可评估的像元。")
            return
        try:
            scores = score_flow_directions_from_cache(self.dem_cache_arrays, self.dem_cache_metadata, all_ops, **self._dem_score_params())
        except Exception as exc:
            messagebox.showerror("DEM评估失败", str(exc))
            return
        summary = summarize_dem_direction_scores(scores)
        preview.dem_score_status = {(score.row, score.col): score.status for score in scores}
        preview.dem_score_summary = summary
        preview.dem_score_label = self._format_dem_score_summary(summary)
        preview.dem_score_details = list(scores)
        self._dem_conflict_cursor = -1
        coverage_text = self._format_dem_cache_coverage(scores)
        self.dem_score_status_var.set(f"{coverage_text}；{preview.dem_score_label}")
        self.info_var.set(f"DEM评估完成：{coverage_text}；{preview.dem_score_label}")
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)

    def locate_next_dem_conflict(self) -> None:
        conflicts = self._dem_conflict_scores()
        if not conflicts:
            messagebox.showinfo("提示", "当前 DEM 评估没有逆坡冲突像元。")
            return
        self._dem_conflict_cursor = (self._dem_conflict_cursor + 1) % len(conflicts)
        score = conflicts[self._dem_conflict_cursor]
        if self.mode_var.get() != "flow":
            self.mode_var.set("flow")
            self.on_tool_changed()
        self.selected_flow_cell = (score.row, score.col)
        self.selected_flow_region = None
        raster = self.flow_raster
        if raster is not None:
            zoom = max(0.1, min(float(self.zoom_var.get()), 16.0))
            self.zoom_var.set(round(zoom, 3))
            self._set_viewport_center(
                score.row + 0.5,
                score.col + 0.5,
                zoom,
                max(1, self.canvas.winfo_width()),
                max(1, self.canvas.winfo_height()),
            )
        drop_text = "" if score.drop is None else f"，高程差 {score.drop:.2f}"
        severity_text = self._dem_score_severity_text(score.severity)
        self.info_var.set(
            f"逆坡冲突 {self._dem_conflict_cursor + 1}/{len(conflicts)}：像元 ({score.row}, {score.col})，方向 {score.code}，{severity_text}{drop_text}"
        )
        self.render(full=False)

    def export_dem_score_report(self) -> None:
        self._export_dem_score_report(only_conflicts=False)

    def export_dem_conflict_report(self) -> None:
        self._export_dem_score_report(only_conflicts=True)

    def _export_dem_score_report(self, only_conflicts: bool = False) -> None:
        scores = list(getattr(self.flow_preview_state, "dem_score_details", []))
        if only_conflicts:
            scores = [score for score in scores if getattr(score, "status", "") == "uphill"]
        if not scores:
            messagebox.showinfo("提示", "当前没有可导出的 DEM 评估结果。")
            return
        prefix = "dem_conflict_report" if only_conflicts else "dem_preview_report"
        default_name = f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            title="导出DEM冲突报告" if only_conflicts else "导出DEM评估报告",
            defaultextension=".csv",
            initialdir=str(self.workspace_dir),
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        out_path = Path(path)
        with out_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["row", "col", "direction_code", "status", "severity", "current_elevation", "next_elevation", "drop", "reason"])
            for score in scores:
                writer.writerow(
                    [
                        score.row,
                        score.col,
                        score.code,
                        self._dem_score_status_text(score.status),
                        self._dem_score_severity_text(score.severity),
                        "" if score.current_elevation is None else f"{score.current_elevation:.6g}",
                        "" if score.next_elevation is None else f"{score.next_elevation:.6g}",
                        "" if score.drop is None else f"{score.drop:.6g}",
                        score.reason,
                    ]
                )
        report_name = "DEM 冲突报告" if only_conflicts else "DEM 评估报告"
        self.info_var.set(f"已导出 {report_name}：{out_path.name}")

    def _format_dem_score_summary(self, summary) -> str:
        uphill_detail = ""
        if int(summary.get("uphill", 0)):
            uphill_detail = (
                f"（轻微 {int(summary.get('uphill_mild', 0))}，"
                f"明显 {int(summary.get('uphill_moderate', 0))}，"
                f"严重 {int(summary.get('uphill_severe', 0))}）"
            )
        return (
            f"顺坡 {int(summary.get('downhill', 0))}，"
            f"近似平坦 {int(summary.get('flat', 0))}，"
            f"逆坡冲突 {int(summary.get('uphill', 0))}{uphill_detail}，"
            f"无DEM {int(summary.get('no_data', 0))}"
        )

    def update_dem_preview_coverage_hint(self) -> None:
        if not hasattr(self, "dem_score_status_var"):
            return
        preview = self.flow_preview_state
        if not preview.has_preview():
            return
        all_ops = list(preview.ops) + list(preview.unchanged_ops)
        if not all_ops:
            return
        if self.dem_cache_arrays is None or self.dem_cache_metadata is None:
            if self.dem_path is not None:
                self.dem_score_status_var.set(f"当前预览 {len(all_ops)} 个像元尚无 DEM 缓存，可先生成锁定范围缓存。")
            else:
                self.dem_score_status_var.set(f"当前预览 {len(all_ops)} 个像元；未加载 DEM。")
            return
        try:
            scores = score_flow_directions_from_cache(self.dem_cache_arrays, self.dem_cache_metadata, all_ops, **self._dem_score_params())
        except Exception as exc:
            self.dem_score_status_var.set(f"DEM缓存覆盖检查失败：{exc}")
            return
        self.dem_score_status_var.set(f"{self._format_dem_cache_coverage(scores)}；可点击“评估当前预览”。")

    def _dem_score_params(self) -> dict:
        flat = self._get_nonnegative_float_var(self.dem_flat_tolerance_var, 1.0)
        mild = self._get_nonnegative_float_var(self.dem_mild_uphill_var, 2.0)
        severe = self._get_nonnegative_float_var(self.dem_severe_uphill_var, 10.0)
        severe = max(mild, severe)
        if severe != self._get_nonnegative_float_var(self.dem_severe_uphill_var, 10.0):
            self.dem_severe_uphill_var.set(severe)
        return {
            "flat_tolerance": flat,
            "mild_uphill_threshold": mild,
            "severe_uphill_threshold": severe,
        }

    def _get_nonnegative_float_var(self, var, fallback: float) -> float:
        try:
            return max(0.0, float(var.get()))
        except Exception:
            var.set(fallback)
            return fallback

    def _format_dem_cache_coverage(self, scores) -> str:
        total = len(scores)
        covered = sum(1 for score in scores if score.status != "no_data")
        ratio = 0.0 if total <= 0 else covered * 100.0 / total
        missing = total - covered
        suggestion = "，建议重新生成更大锁定范围缓存" if missing > 0 else ""
        return f"DEM缓存覆盖 {covered}/{total} ({ratio:.1f}%)，无DEM {missing}{suggestion}"

    def _dem_conflict_scores(self):
        return [score for score in getattr(self.flow_preview_state, "dem_score_details", []) if getattr(score, "status", "") == "uphill"]

    def _dem_score_status_text(self, status: str) -> str:
        return {
            "downhill": "顺坡",
            "flat": "近似平坦",
            "uphill": "逆坡冲突",
            "no_data": "无DEM",
        }.get(status, status)

    def _dem_score_severity_text(self, severity: str) -> str:
        return {
            "mild": "轻微",
            "moderate": "明显",
            "severe": "严重",
        }.get(severity, "")

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

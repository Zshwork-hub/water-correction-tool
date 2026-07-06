from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from water_tool.water_core import AscHeader, RasterData
from water_tool.water_dem import (
    build_dem_cache,
    DemCacheCancelled,
    dem_cache_matches,
    load_dem_cache,
    plan_dem_window,
    raster_cell_bounds,
    read_dem_metadata,
    save_dem_cache,
    score_flow_directions_from_cache,
    summarize_dem_for_raster_cells,
    summarize_dem_direction_scores,
    summarize_dem_window,
    transform_bounds_to_dem,
)


class DemSupportTests(unittest.TestCase):
    def _write_tiny_dem(self, path: Path) -> None:
        data = np.arange(100, dtype=np.int16).reshape((10, 10))
        data[0, 0] = -9999
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="int16",
            crs="EPSG:4326",
            transform=from_origin(0, 10, 1, 1),
            nodata=-9999,
        ) as ds:
            ds.write(data, 1)

    def _make_tiny_raster(self, path: Path) -> RasterData:
        raw = [
            "ncols 2\n",
            "nrows 2\n",
            "xllcorner 0\n",
            "yllcorner 0\n",
            "cellsize 5\n",
            "NODATA_value -9999\n",
        ]
        header = AscHeader(
            raw,
            {
                "ncols": 2,
                "nrows": 2,
                "xllcorner": 0,
                "yllcorner": 0,
                "cellsize": 5,
                "nodata_value": -9999,
            },
        )
        return RasterData(path, header, np.ones((2, 2), dtype=np.int32), "EPSG:4326")

    def test_read_dem_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiny.tif"
            self._write_tiny_dem(path)

            meta = read_dem_metadata(path)

            self.assertEqual(meta.driver, "GTiff")
            self.assertEqual(meta.width, 10)
            self.assertEqual(meta.height, 10)
            self.assertEqual(meta.count, 1)
            self.assertEqual(meta.crs_text, "EPSG:4326")
            self.assertEqual(meta.resolution, (1.0, 1.0))
            self.assertEqual(meta.transform, (1.0, 0.0, 0.0, 0.0, -1.0, 10.0))
            self.assertEqual(meta.nodata, -9999.0)

    def test_plan_dem_window_clips_and_respects_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiny.tif"
            self._write_tiny_dem(path)

            plan = plan_dem_window(path, (2, 4, 5, 8), max_pixels=20)

            self.assertTrue(plan.readable)
            self.assertEqual(plan.pixel_count, 12)
            self.assertFalse(plan.too_large)
            self.assertIsNotNone(plan.window)

            too_large = plan_dem_window(path, (0, 0, 10, 10), max_pixels=50)
            self.assertFalse(too_large.readable)
            self.assertTrue(too_large.too_large)
            self.assertIn("超过当前上限", too_large.reason)

    def test_plan_dem_window_warns_before_default_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiny.tif"
            self._write_tiny_dem(path)

            plan = plan_dem_window(path, (0, 0, 10, 10), warning_pixels=50, max_pixels=200, hard_max_pixels=500)

            self.assertTrue(plan.readable)
            self.assertFalse(plan.too_large)
            self.assertFalse(plan.hard_blocked)
            self.assertTrue(plan.warning)
            self.assertIn("提示阈值", plan.reason)

    def test_plan_dem_window_blocks_hard_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiny.tif"
            self._write_tiny_dem(path)

            plan = plan_dem_window(path, (0, 0, 10, 10), warning_pixels=10, max_pixels=200, hard_max_pixels=80)

            self.assertFalse(plan.readable)
            self.assertTrue(plan.too_large)
            self.assertTrue(plan.hard_blocked)
            self.assertIn("硬上限", plan.reason)

    def test_summarize_dem_window_ignores_nodata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiny.tif"
            self._write_tiny_dem(path)
            plan = plan_dem_window(path, (0, 9, 2, 10), max_pixels=10)
            self.assertTrue(plan.readable)
            assert plan.window is not None

            summary = summarize_dem_window(path, plan.window)

            self.assertEqual(summary.pixel_count, 2)
            self.assertEqual(summary.valid_count, 1)
            self.assertEqual(summary.nodata_count, 1)
            self.assertEqual(summary.min_elevation, 1.0)
            self.assertEqual(summary.max_elevation, 1.0)

    def test_transform_bounds_to_dem_keeps_bounds_in_same_crs(self) -> None:
        bounds = transform_bounds_to_dem((1, 2, 3, 4), "EPSG:4326", "EPSG:4326")

        self.assertEqual(bounds, (1.0, 2.0, 3.0, 4.0))

    def test_raster_cell_bounds_uses_cell_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raster = self._make_tiny_raster(Path(tmp) / "grid.asc")

            self.assertEqual(raster_cell_bounds(raster, 0, 0), (0, 5, 5, 10))
            self.assertEqual(raster_cell_bounds(raster, 1, 1), (5, 0, 10, 5))

    def test_summarize_dem_for_raster_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")

            summaries = summarize_dem_for_raster_cells(dem_path, raster, [(0, 0), (1, 1)])

            self.assertEqual(len(summaries), 2)
            first = summaries[0]
            self.assertTrue(first.readable)
            self.assertEqual(first.pixel_count, 25)
            self.assertEqual(first.valid_count, 24)
            self.assertEqual(first.nodata_count, 1)
            self.assertEqual(first.min_elevation, 1.0)
            self.assertEqual(first.max_elevation, 44.0)
            self.assertEqual(first.median_elevation, 22.5)

            second = summaries[1]
            self.assertTrue(second.readable)
            self.assertEqual(second.pixel_count, 25)
            self.assertEqual(second.valid_count, 25)
            self.assertEqual(second.min_elevation, 55.0)
            self.assertEqual(second.max_elevation, 99.0)

    def test_summarize_dem_for_raster_cells_reports_blocked_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")

            summaries = summarize_dem_for_raster_cells(dem_path, raster, [(0, 0)], max_pixels_per_cell=10)

            self.assertEqual(len(summaries), 1)
            self.assertFalse(summaries[0].readable)
            self.assertEqual(summaries[0].valid_count, 0)
            self.assertIn("超过当前上限", summaries[0].reason)

    def test_build_dem_cache_for_partial_raster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")

            result = build_dem_cache(dem_path, raster, row_range=(0, 2), col_range=(0, 2))

            self.assertEqual(result.row_range, (0, 2))
            self.assertEqual(result.col_range, (0, 2))
            self.assertEqual(result.processed_cells, 4)
            self.assertEqual(result.readable_cells, 4)
            self.assertEqual(result.blocked_cells, 0)
            self.assertEqual(result.arrays["median"].shape, (2, 2))
            self.assertEqual(result.arrays["median"].dtype, np.float32)
            self.assertEqual(result.arrays["valid_count"].dtype, np.int32)
            self.assertEqual(result.arrays["readable"].dtype, np.uint8)
            self.assertAlmostEqual(float(result.arrays["median"][0, 0]), 22.5)
            self.assertEqual(int(result.arrays["valid_count"][0, 0]), 24)
            self.assertEqual(int(result.arrays["nodata_count"][0, 0]), 1)
            self.assertEqual(int(result.arrays["pixel_count"][0, 0]), 25)
            self.assertEqual(float(result.arrays["min"][1, 1]), 55.0)
            self.assertEqual(float(result.arrays["max"][1, 1]), 99.0)
            self.assertEqual(result.metadata["window"], {"row0": 0, "row1": 2, "col0": 0, "col1": 2})
            self.assertEqual(result.metadata["stats"]["processed_cells"], 4)

    def test_save_load_and_match_dem_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")
            result = build_dem_cache(dem_path, raster, row_range=(0, 1), col_range=(0, 2))
            data_path = root / "cache.npz"
            meta_path = root / "cache.json"

            save_dem_cache(data_path, meta_path, result)
            arrays, metadata = load_dem_cache(data_path, meta_path)

            self.assertTrue(data_path.exists())
            self.assertTrue(meta_path.exists())
            np.testing.assert_array_equal(arrays["valid_count"], result.arrays["valid_count"])
            np.testing.assert_allclose(arrays["median"], result.arrays["median"])
            self.assertEqual(metadata["window"], {"row0": 0, "row1": 1, "col0": 0, "col1": 2})
            self.assertTrue(dem_cache_matches(metadata, dem_path, raster))
            self.assertTrue(dem_cache_matches(metadata, dem_path, raster, row_range=(0, 1), col_range=(0, 2)))
            self.assertFalse(dem_cache_matches(metadata, dem_path, raster, row_range=(0, 2), col_range=(0, 2)))

    def test_dem_cache_invalidates_when_inputs_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")
            result = build_dem_cache(dem_path, raster, row_range=(0, 1), col_range=(0, 1))
            metadata = result.metadata

            changed_raster = self._make_tiny_raster(root / "grid_changed.asc")
            changed_raster.header.values["cellsize"] = 4
            self.assertFalse(dem_cache_matches(metadata, dem_path, changed_raster, row_range=(0, 1), col_range=(0, 1)))

            time.sleep(0.01)
            dem_path.touch()
            self.assertFalse(dem_cache_matches(metadata, dem_path, raster, row_range=(0, 1), col_range=(0, 1)))

    def test_build_dem_cache_reports_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")
            calls = []

            result = build_dem_cache(
                dem_path,
                raster,
                progress_callback=lambda done, total, readable, blocked: calls.append((done, total, readable, blocked)),
                progress_interval_cells=2,
            )

            self.assertEqual(result.processed_cells, 4)
            self.assertGreaterEqual(len(calls), 3)
            self.assertEqual(calls[0], (0, 4, 0, 0))
            self.assertEqual(calls[-1][0], 4)
            self.assertEqual(calls[-1][1], 4)

    def test_build_dem_cache_can_be_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dem_path = root / "tiny.tif"
            self._write_tiny_dem(dem_path)
            raster = self._make_tiny_raster(root / "grid.asc")
            should_cancel = {"value": False}

            def progress(done: int, _total: int, _readable: int, _blocked: int) -> None:
                if done >= 2:
                    should_cancel["value"] = True

            with self.assertRaises(DemCacheCancelled):
                build_dem_cache(
                    dem_path,
                    raster,
                    progress_callback=progress,
                    cancel_checker=lambda: should_cancel["value"],
                    progress_interval_cells=2,
                )

    def test_score_flow_directions_from_cache(self) -> None:
        arrays = {
            "median": np.array(
                [
                    [100.0, 90.0, 90.4, 90.0],
                    [110.0, 91.5, 95.0, 120.0],
                ],
                dtype=np.float32,
            ),
            "readable": np.array(
                [
                    [1, 1, 1, 1],
                    [1, 1, 1, 0],
                ],
                dtype=np.uint8,
            ),
        }
        metadata = {"window": {"row0": 10, "row1": 12, "col0": 20, "col1": 24}}
        ops = [
            (10, 20, 1),   # east, 100 -> 90
            (10, 21, 1),   # east, 90 -> 90.4
            (10, 21, 4),   # south, 90 -> 91.5
            (10, 22, 4),   # south, 90.4 -> 95
            (10, 23, 4),   # south, target unreadable
            (9, 20, 1),    # outside cache
        ]

        scores = score_flow_directions_from_cache(arrays, metadata, ops, flat_tolerance=1.0)
        summary = summarize_dem_direction_scores(scores)

        self.assertEqual([score.status for score in scores], ["downhill", "flat", "uphill", "uphill", "no_data", "no_data"])
        self.assertEqual([score.severity for score in scores], ["", "", "mild", "moderate", "", ""])
        self.assertAlmostEqual(scores[0].drop or 0.0, 10.0)
        self.assertEqual(summary["downhill"], 1)
        self.assertEqual(summary["flat"], 1)
        self.assertEqual(summary["uphill"], 2)
        self.assertEqual(summary["uphill_mild"], 1)
        self.assertEqual(summary["uphill_moderate"], 1)
        self.assertEqual(summary["uphill_severe"], 0)
        self.assertEqual(summary["no_data"], 2)

    def test_score_flow_directions_marks_severe_uphill(self) -> None:
        arrays = {
            "median": np.array([[10.0], [40.0]], dtype=np.float32),
            "readable": np.ones((2, 1), dtype=np.uint8),
        }
        metadata = {"window": {"row0": 0, "row1": 2, "col0": 0, "col1": 1}}

        scores = score_flow_directions_from_cache(arrays, metadata, [(0, 0, 4)], flat_tolerance=1.0)
        summary = summarize_dem_direction_scores(scores)

        self.assertEqual(scores[0].status, "uphill")
        self.assertEqual(scores[0].severity, "severe")
        self.assertEqual(summary["uphill_severe"], 1)


if __name__ == "__main__":
    unittest.main()

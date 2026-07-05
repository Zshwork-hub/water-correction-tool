from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from water_tool.water_core import AscHeader, RasterData
from water_tool.water_dem import (
    plan_dem_window,
    raster_cell_bounds,
    read_dem_metadata,
    summarize_dem_for_raster_cells,
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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from water_tool.water_dem import plan_dem_window, read_dem_metadata, summarize_dem_window, transform_bounds_to_dem


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
            self.assertIn("超过上限", too_large.reason)

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


if __name__ == "__main__":
    unittest.main()

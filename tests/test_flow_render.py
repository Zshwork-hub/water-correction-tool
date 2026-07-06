from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from water_tool.water_core import AscHeader, RasterData
from water_tool.water_flow_render import FlowRenderMixin


def tiny_raster() -> RasterData:
    header = AscHeader(
        [
            "ncols 2\n",
            "nrows 2\n",
            "xllcorner 0\n",
            "yllcorner 0\n",
            "cellsize 1\n",
            "NODATA_value -9999\n",
        ],
        {
            "ncols": 2,
            "nrows": 2,
            "xllcorner": 0,
            "yllcorner": 0,
            "cellsize": 1,
            "nodata_value": -9999,
        },
    )
    return RasterData(Path("flow.asc"), header, np.ones((2, 2), dtype=np.int32))


class DummyVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FlowRenderHarness(FlowRenderMixin):
    def __init__(self, display_mode: str) -> None:
        self._view_x = 0.0
        self._view_y = 0.0
        self.dem_score_display_var = DummyVar(display_mode)


class FlowRenderTests(unittest.TestCase):
    def _render_dem_scores(self, display_mode: str) -> np.ndarray:
        harness = FlowRenderHarness(display_mode)
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        harness._draw_dem_score_overlay(
            draw,
            image,
            tiny_raster(),
            10.0,
            {
                (0, 0): "downhill",
                (0, 1): "uphill",
            },
        )
        return np.asarray(image)

    def test_dem_score_display_mode_all_draws_all_statuses(self) -> None:
        pixels = self._render_dem_scores("全部")

        self.assertGreater(np.count_nonzero((pixels[:, :, 1] > 120) & (pixels[:, :, 0] < 80)), 0)
        self.assertGreater(np.count_nonzero((pixels[:, :, 0] > 180) & (pixels[:, :, 1] < 80)), 0)

    def test_dem_score_display_mode_conflicts_draws_only_uphill(self) -> None:
        pixels = self._render_dem_scores("仅冲突")

        self.assertEqual(np.count_nonzero((pixels[:, :, 1] > 120) & (pixels[:, :, 0] < 80)), 0)
        self.assertGreater(np.count_nonzero((pixels[:, :, 0] > 180) & (pixels[:, :, 1] < 80)), 0)

    def test_dem_score_display_mode_hidden_draws_nothing(self) -> None:
        pixels = self._render_dem_scores("隐藏")

        self.assertEqual(np.count_nonzero(pixels[:, :, 3]), 0)


if __name__ == "__main__":
    unittest.main()

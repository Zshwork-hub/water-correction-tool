from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from water_tool.water_core import AscHeader, RasterData, relative_or_absolute, resolve_relative_or_absolute
from water_tool.water_project import (
    project_data_path,
    raster_payload,
    read_project_arrays,
    read_project_files,
    read_project_payload,
    read_session_files,
    rebuild_raster,
    write_project_files,
    write_session_files,
)


def tiny_header(nrows: int = 2, ncols: int = 3) -> AscHeader:
    raw = [
        f"ncols {ncols}\n",
        f"nrows {nrows}\n",
        "xllcorner 0\n",
        "yllcorner 0\n",
        "cellsize 1\n",
        "NODATA_value -9999\n",
    ]
    return AscHeader(
        raw,
        {
            "ncols": ncols,
            "nrows": nrows,
            "xllcorner": 0,
            "yllcorner": 0,
            "cellsize": 1,
            "nodata_value": -9999,
        },
    )


def make_raster(path: Path, data: np.ndarray, crs_text: str = "") -> RasterData:
    return RasterData(path, tiny_header(*data.shape), data.astype(np.int32), crs_text)


class ProjectPersistenceTests(unittest.TestCase):
    def test_project_files_round_trip_payload_and_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            stream = make_raster(workspace / "stream.asc", np.array([[1, -9999, 1], [-9999, 1, -9999]]), "stream-prj")
            flow = make_raster(workspace / "flow.asc", np.array([[1, 2, 4], [8, 16, 32]]), "flow-prj")
            project_path = root / "case.waterproj"
            data_path = project_data_path(project_path)

            def store(path: Path) -> str:
                return relative_or_absolute(path, root)

            def resolve(stored: str) -> Path:
                return resolve_relative_or_absolute(stored, root)

            payload = {
                "version": "2.0",
                "workspace_dir": str(workspace),
                "data_path": store(data_path),
                "stream": raster_payload(stream, store),
                "flow": raster_payload(flow, store),
                "note": "中文路径和说明保持 UTF-8",
            }

            write_project_files(project_path, data_path, payload, stream, flow, stream.copy(), flow.copy())

            loaded_payload = read_project_payload(project_path)
            self.assertEqual(loaded_payload["note"], "中文路径和说明保持 UTF-8")
            result = read_project_files(project_path, resolve)
            self.assertIsNone(result.data_error)
            self.assertIsNotNone(result.arrays)
            assert result.arrays is not None
            np.testing.assert_array_equal(result.arrays["stream"], stream.data)
            np.testing.assert_array_equal(result.arrays["flow"], flow.data)
            rebuilt = rebuild_raster(loaded_payload["stream"], result.arrays["stream"], resolve)
            self.assertIsNotNone(rebuilt)
            assert rebuilt is not None
            self.assertEqual(rebuilt.path, stream.path.resolve())
            self.assertEqual(rebuilt.crs_text, "stream-prj")
            np.testing.assert_array_equal(rebuilt.data, stream.data)

    def test_project_read_handles_missing_and_corrupt_data_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_payload = {"data_path": "missing.waterproj.npz"}
            missing = read_project_arrays(missing_payload, lambda stored: resolve_relative_or_absolute(stored, root))
            self.assertIsNone(missing.arrays)
            self.assertIsNone(missing.data_error)

            corrupt_path = root / "broken.waterproj.npz"
            corrupt_path.write_text("not an npz", encoding="utf-8")
            corrupt_payload = {"data_path": corrupt_path.name}
            corrupt = read_project_arrays(corrupt_payload, lambda stored: resolve_relative_or_absolute(stored, root))
            self.assertIsNone(corrupt.arrays)
            self.assertIsNotNone(corrupt.data_error)

    def test_session_files_round_trip_and_missing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "autosave.json"
            data_path = root / "autosave.npz"
            self.assertIsNone(read_session_files(meta_path, data_path))

            stream = make_raster(root / "stream.asc", np.array([[1, 1, -9999], [-9999, 1, -9999]]))
            flow = make_raster(root / "flow.asc", np.array([[1, 2, 4], [8, 16, 32]]))
            meta = {
                "mode": "flow",
                "stream": raster_payload(stream, lambda path: relative_or_absolute(path, root)),
                "flow": raster_payload(flow, lambda path: relative_or_absolute(path, root)),
            }

            write_session_files(meta_path, data_path, meta, stream, flow, stream.copy(), flow.copy())
            result = read_session_files(meta_path, data_path)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.payload["mode"], "flow")
            self.assertIsNotNone(result.arrays)
            assert result.arrays is not None
            np.testing.assert_array_equal(result.arrays["stream"], stream.data)
            np.testing.assert_array_equal(result.arrays["original_flow"], flow.data)

    def test_rebuild_raster_rejects_mismatched_array_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raster = make_raster(root / "flow.asc", np.array([[1, 2, 4], [8, 16, 32]]))
            payload = raster_payload(raster, lambda path: relative_or_absolute(path, root))
            bad_data = np.array([[1, 2], [4, 8]], dtype=np.int32)

            rebuilt = rebuild_raster(payload, bad_data, lambda stored: resolve_relative_or_absolute(stored, root))

            self.assertIsNone(rebuilt)


if __name__ == "__main__":
    unittest.main()

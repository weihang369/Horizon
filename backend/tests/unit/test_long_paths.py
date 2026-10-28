"""The v1.1 runtime hunt: on Windows with long paths off, a clone in a deep folder can't save its generated images
(a portrait's temp file is about 140 characters below `data/`). The backend warns at start-up."""

from __future__ import annotations

from pathlib import Path

from horizon.runtime import long_path_warning

SHORT = Path("C:/Users/kai/Documents/GitHub/Horizon/data")
DEEP = Path("C:/Users/kai/AppData/Local/Temp/" + "x" * 90 + "/Horizon/data")


def test_a_deep_folder_on_windows_without_long_paths_is_warned_about() -> None:
    w = long_path_warning(DEEP, windows=True, long_paths=False)
    assert w is not None and f"{len(str(DEEP))} characters" in w and "long paths" in w


def test_no_warning_for_a_short_folder_long_paths_on_or_another_system() -> None:
    assert long_path_warning(SHORT, windows=True, long_paths=False) is None
    assert long_path_warning(DEEP, windows=True, long_paths=True) is None
    assert long_path_warning(DEEP, windows=False, long_paths=False) is None

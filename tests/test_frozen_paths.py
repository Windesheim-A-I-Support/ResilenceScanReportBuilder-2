"""
test_frozen_paths.py — tests for frozen-app vs dev path resolution.

Covers utils.path_utils.get_user_base_dir() under all four conditions:
  - dev mode (default in test runner)
  - frozen + win32
  - frozen + linux
  - frozen + win32 with no APPDATA env var
"""

import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _reimport(monkeypatch_or_none=None):
    """Force-reimport utils.path_utils so module-level state is fresh."""
    import utils.path_utils as m

    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# dev mode
# ---------------------------------------------------------------------------


def test_dev_mode_returns_repo_root():
    """In dev mode (not frozen) get_user_base_dir() returns the repo root."""
    from utils.path_utils import get_user_base_dir

    result = get_user_base_dir()
    # In dev mode the result is two levels up from utils/ == repo root
    assert result == ROOT
    assert result.is_dir()


# ---------------------------------------------------------------------------
# frozen + win32
# ---------------------------------------------------------------------------


def test_frozen_win32_uses_appdata(monkeypatch, tmp_path):
    """Frozen+win32: result is %APPDATA%\\ResilienceScan."""
    fake_appdata = str(tmp_path / "AppData" / "Roaming")
    monkeypatch.setenv("APPDATA", fake_appdata)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    import utils.path_utils as m

    importlib.reload(m)
    result = m.get_user_base_dir()
    assert result == pathlib.Path(fake_appdata) / "ResilienceScan"


def test_frozen_win32_no_appdata_falls_back_to_home(monkeypatch):
    """Frozen+win32 with no APPDATA env: falls back to Path.home()."""
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    import utils.path_utils as m

    importlib.reload(m)
    result = m.get_user_base_dir()
    # Path.home() is used as fallback
    assert result == pathlib.Path.home() / "ResilienceScan"


# ---------------------------------------------------------------------------
# frozen + darwin
# ---------------------------------------------------------------------------


def test_frozen_darwin_uses_library_path(monkeypatch):
    """Frozen+darwin: result is ~/Library/Application Support/ResilienceScan."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")

    import utils.path_utils as m

    importlib.reload(m)
    result = m.get_user_base_dir()
    assert (
        result
        == pathlib.Path.home() / "Library" / "Application Support" / "ResilienceScan"
    )


def test_frozen_darwin_not_appdata(monkeypatch, tmp_path):
    """Frozen+darwin should NOT use APPDATA or .local/share."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")

    import utils.path_utils as m

    importlib.reload(m)
    result = m.get_user_base_dir()
    assert "AppData" not in str(result)
    assert ".local" not in str(result)
    assert "Library" in str(result)


# ---------------------------------------------------------------------------
# frozen + linux
# ---------------------------------------------------------------------------


def test_frozen_linux_uses_xdg_path(monkeypatch):
    """Frozen+linux: result is ~/.local/share/resiliencescan."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    import utils.path_utils as m

    importlib.reload(m)
    result = m.get_user_base_dir()
    assert result == pathlib.Path.home() / ".local" / "share" / "resiliencescan"


def test_frozen_linux_not_appdata(monkeypatch, tmp_path):
    """Frozen+linux should NOT use APPDATA even if set."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    import utils.path_utils as m

    importlib.reload(m)
    result = m.get_user_base_dir()
    assert "AppData" not in str(result)
    assert "resiliencescan" in str(result).lower()


# ---------------------------------------------------------------------------
# return type
# ---------------------------------------------------------------------------


def test_returns_path_object():
    """get_user_base_dir() always returns a pathlib.Path."""
    from utils.path_utils import get_user_base_dir

    result = get_user_base_dir()
    assert isinstance(result, pathlib.Path)


# ---------------------------------------------------------------------------
# cleanup: restore sys.frozen after monkeypatched tests
# ---------------------------------------------------------------------------
# pytest's monkeypatch fixture handles teardown automatically, but we must
# reload the module after each test that patched sys.frozen so subsequent
# tests see the original dev-mode behaviour.


@pytest.fixture(autouse=True)
def _reload_path_utils_after():
    yield
    import utils.path_utils as m

    importlib.reload(m)


# ---------------------------------------------------------------------------
# _sync_template() tests
# ---------------------------------------------------------------------------


def _make_sync_template(monkeypatch, src_dir, dst_dir):
    """Reload app.app_paths with _asset_root → src_dir and _data_root → dst_dir."""
    import app.app_paths as ap

    monkeypatch.setattr(ap, "_asset_root", lambda: src_dir)
    monkeypatch.setattr(ap, "_data_root", lambda: dst_dir)
    return ap._sync_template


def test_sync_template_skips_when_not_frozen(monkeypatch, tmp_path):
    """In dev mode _sync_template() returns without copying anything."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    import app.app_paths as ap

    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    (src / "ResilienceReport.qmd").write_text("hello", encoding="utf-8")

    monkeypatch.setattr(ap, "_asset_root", lambda: src)
    monkeypatch.setattr(ap, "_data_root", lambda: dst)
    ap._sync_template()

    assert not dst.exists()


def test_sync_template_copies_when_dst_missing(monkeypatch, tmp_path):
    """When frozen and dst QMD is absent, _sync_template() copies the file."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    import app.app_paths as ap

    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    (src / "ResilienceReport.qmd").write_text("v2", encoding="utf-8")

    monkeypatch.setattr(ap, "_asset_root", lambda: src)
    monkeypatch.setattr(ap, "_data_root", lambda: dst)
    ap._sync_template()

    assert (dst / "ResilienceReport.qmd").read_text(encoding="utf-8") == "v2"


def test_sync_template_skips_when_dst_newer(monkeypatch, tmp_path):
    """When frozen and dst QMD is newer than src, _sync_template() skips copy."""
    import os
    import time

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    import app.app_paths as ap

    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.mkdir()

    src_qmd = src / "ResilienceReport.qmd"
    dst_qmd = dst / "ResilienceReport.qmd"
    src_qmd.write_text("old", encoding="utf-8")
    dst_qmd.write_text("current", encoding="utf-8")

    # Make dst newer than src
    t = time.time()
    os.utime(src_qmd, (t - 100, t - 100))
    os.utime(dst_qmd, (t, t))

    monkeypatch.setattr(ap, "_asset_root", lambda: src)
    monkeypatch.setattr(ap, "_data_root", lambda: dst)
    ap._sync_template()

    # dst should still contain "current" — no copy happened
    assert dst_qmd.read_text(encoding="utf-8") == "current"


def test_sync_template_copies_when_src_newer(monkeypatch, tmp_path):
    """When frozen and src QMD is newer than dst, _sync_template() re-copies."""
    import os
    import time

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    import app.app_paths as ap

    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.mkdir()

    src_qmd = src / "ResilienceReport.qmd"
    dst_qmd = dst / "ResilienceReport.qmd"
    src_qmd.write_text("updated", encoding="utf-8")
    dst_qmd.write_text("stale", encoding="utf-8")

    # Make src newer than dst
    t = time.time()
    os.utime(dst_qmd, (t - 100, t - 100))
    os.utime(src_qmd, (t, t))

    monkeypatch.setattr(ap, "_asset_root", lambda: src)
    monkeypatch.setattr(ap, "_data_root", lambda: dst)
    ap._sync_template()

    assert dst_qmd.read_text(encoding="utf-8") == "updated"

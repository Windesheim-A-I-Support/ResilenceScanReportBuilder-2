"""
test_path_functions.py — unit tests for app.app_paths path-resolution helpers.

Covers:
- _asset_root(): dev → repo root; frozen → sys._MEIPASS
- _data_root(): dev → repo root; frozen win32/darwin/linux → platform dirs
- _r_library_path(): dev → None; frozen → exe.parent/r-library
- _bundled_dir(): dev → None; frozen + exists → Path; frozen + absent → None
- make_subprocess_env(): no bundled tools; R_LIBS prepended; bundled PATH prepended
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.app_paths as ap  # noqa: E402


# ---------------------------------------------------------------------------
# _asset_root
# ---------------------------------------------------------------------------


def test_asset_root_dev_mode_is_repo_root(monkeypatch):
    """In dev mode _asset_root() returns the repo root (parent of app/)."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert ap._asset_root() == ROOT


def test_asset_root_frozen_returns_meipass(monkeypatch, tmp_path):
    """In frozen mode _asset_root() returns Path(sys._MEIPASS)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ap._asset_root() == tmp_path


# ---------------------------------------------------------------------------
# _data_root
# ---------------------------------------------------------------------------


def test_data_root_dev_mode_is_repo_root(monkeypatch):
    """In dev mode _data_root() returns the repo root."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert ap._data_root() == ROOT


def test_data_root_frozen_win32(monkeypatch, tmp_path):
    """Frozen+win32: _data_root() returns %APPDATA%/ResilienceScan."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert ap._data_root() == tmp_path / "ResilienceScan"


def test_data_root_frozen_darwin(monkeypatch):
    """Frozen+darwin: _data_root() returns ~/Library/Application Support/ResilienceScan."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert (
        ap._data_root()
        == Path.home() / "Library" / "Application Support" / "ResilienceScan"
    )


def test_data_root_frozen_linux(monkeypatch):
    """Frozen+linux: _data_root() returns ~/.local/share/resiliencescan."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert ap._data_root() == Path.home() / ".local" / "share" / "resiliencescan"


def test_data_root_frozen_win32_no_appdata_falls_back(monkeypatch):
    """Frozen+win32 with no APPDATA: falls back to Path.home()/ResilienceScan."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    assert ap._data_root() == Path.home() / "ResilienceScan"


# ---------------------------------------------------------------------------
# _r_library_path
# ---------------------------------------------------------------------------


def test_r_library_path_dev_returns_none(monkeypatch):
    """In dev mode _r_library_path() returns None."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert ap._r_library_path() is None


def test_r_library_path_frozen_returns_sibling(monkeypatch, tmp_path):
    """In frozen mode _r_library_path() returns exe.parent/r-library."""
    fake_exe = tmp_path / "ResilenceScanReportBuilder-2"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    assert ap._r_library_path() == tmp_path / "r-library"


# ---------------------------------------------------------------------------
# _bundled_dir
# ---------------------------------------------------------------------------


def test_bundled_dir_dev_returns_none(monkeypatch):
    """In dev mode _bundled_dir() returns None."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert ap._bundled_dir() is None


def test_bundled_dir_frozen_exists(monkeypatch, tmp_path):
    """In frozen mode _bundled_dir() returns _MEIPASS/bundled when it exists."""
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ap._bundled_dir() == bundled


def test_bundled_dir_frozen_absent(monkeypatch, tmp_path):
    """In frozen mode _bundled_dir() returns None when bundled/ is absent."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ap._bundled_dir() is None


# ---------------------------------------------------------------------------
# make_subprocess_env
# ---------------------------------------------------------------------------


def test_make_subprocess_env_returns_dict(monkeypatch):
    """make_subprocess_env() always returns a dict."""
    monkeypatch.setattr(ap, "_bundled_dir", lambda: None)
    monkeypatch.setattr(ap, "_r_library_path", lambda: None)
    env = ap.make_subprocess_env()
    assert isinstance(env, dict)


def test_make_subprocess_env_prepends_r_libs(monkeypatch, tmp_path):
    """When r-library exists, R_LIBS is set (or prepended) with its path."""
    r_lib = tmp_path / "r-library"
    r_lib.mkdir()
    monkeypatch.setattr(ap, "_bundled_dir", lambda: None)
    monkeypatch.setattr(ap, "_r_library_path", lambda: r_lib)
    env = ap.make_subprocess_env()
    assert str(r_lib) in env.get("R_LIBS", "")


def test_make_subprocess_env_r_libs_absent_not_set(monkeypatch, tmp_path):
    """When r-library path does not exist on disk, R_LIBS is not modified."""
    monkeypatch.setattr(ap, "_bundled_dir", lambda: None)
    monkeypatch.setattr(ap, "_r_library_path", lambda: tmp_path / "nonexistent")
    monkeypatch.delenv("R_LIBS", raising=False)
    env = ap.make_subprocess_env()
    assert "R_LIBS" not in env


def test_make_subprocess_env_bundled_quarto_in_path(monkeypatch, tmp_path):
    """When bundled/quarto/bin exists, PATH includes it."""
    bundled = tmp_path / "bundled"
    quarto_bin = bundled / "quarto" / "bin"
    quarto_bin.mkdir(parents=True)
    monkeypatch.setattr(ap, "_bundled_dir", lambda: bundled)
    monkeypatch.setattr(ap, "_r_library_path", lambda: None)
    env = ap.make_subprocess_env()
    assert str(quarto_bin) in env.get("PATH", "")


def test_make_subprocess_env_bundled_tinytex_in_path(monkeypatch, tmp_path):
    """When bundled/tinytex/bin/<arch> exists, PATH includes the arch dir."""
    bundled = tmp_path / "bundled"
    tinytex_arch = bundled / "tinytex" / "bin" / "x86_64-linux"
    tinytex_arch.mkdir(parents=True)
    monkeypatch.setattr(ap, "_bundled_dir", lambda: bundled)
    monkeypatch.setattr(ap, "_r_library_path", lambda: None)
    env = ap.make_subprocess_env()
    assert str(tinytex_arch) in env.get("PATH", "")


def test_make_subprocess_env_r_framework_sets_r_home(monkeypatch, tmp_path):
    """When bundled/R.framework/Resources exists, R_HOME is set."""
    bundled = tmp_path / "bundled"
    r_resources = bundled / "R.framework" / "Resources"
    r_resources.mkdir(parents=True)
    monkeypatch.setattr(ap, "_bundled_dir", lambda: bundled)
    monkeypatch.setattr(ap, "_r_library_path", lambda: None)
    env = ap.make_subprocess_env()
    assert env.get("R_HOME") == str(r_resources)

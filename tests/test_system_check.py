"""
test_system_check.py — unit tests for gui_system_check utility functions.

Covers:
- _bundled_tool(): dev mode → None; frozen + exists → path; frozen + absent → None
- _refresh_windows_path(): no-op on non-Windows platforms
- _find_quarto(): PATH hit; Windows fixed path; Darwin candidate; not found
- _find_tlmgr(): PATH hit; Darwin candidate (.TinyTeX); Linux candidate; not found
- setup_status(): complete_pass, complete_fail, running, unknown, OSError
- _r_lib_path(): dev → None; frozen + dir exists → Path; frozen + absent → None
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gui_system_check as gsc  # noqa: E402


# ---------------------------------------------------------------------------
# _bundled_tool
# ---------------------------------------------------------------------------


def test_bundled_tool_dev_mode_returns_none(monkeypatch):
    """In dev (non-frozen) mode, always returns None."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert gsc._bundled_tool("quarto/bin/quarto") is None


def test_bundled_tool_frozen_file_exists(monkeypatch, tmp_path):
    """In frozen mode, returns absolute path when the file exists."""
    tool = tmp_path / "bundled" / "quarto" / "bin" / "quarto"
    tool.parent.mkdir(parents=True)
    tool.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    result = gsc._bundled_tool("quarto/bin/quarto")
    assert result == str(tool)


def test_bundled_tool_frozen_file_missing(monkeypatch, tmp_path):
    """In frozen mode, returns None when the file is absent."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert gsc._bundled_tool("quarto/bin/quarto") is None


# ---------------------------------------------------------------------------
# _refresh_windows_path
# ---------------------------------------------------------------------------


def test_refresh_windows_path_noop_on_linux(monkeypatch):
    """On Linux the function returns immediately without touching PATH."""
    monkeypatch.setattr(sys, "platform", "linux")
    original = os.environ.get("PATH", "")
    gsc._refresh_windows_path()
    assert os.environ.get("PATH", "") == original


def test_refresh_windows_path_noop_on_darwin(monkeypatch):
    """On macOS the function returns immediately without touching PATH."""
    monkeypatch.setattr(sys, "platform", "darwin")
    original = os.environ.get("PATH", "")
    gsc._refresh_windows_path()
    assert os.environ.get("PATH", "") == original


# ---------------------------------------------------------------------------
# _find_quarto
# ---------------------------------------------------------------------------


def test_find_quarto_found_on_path(monkeypatch):
    """Returns the PATH result when quarto is on PATH."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        "gui_system_check.shutil.which",
        lambda n: "/usr/bin/quarto" if n == "quarto" else None,
    )
    assert gsc._find_quarto() == "/usr/bin/quarto"


def test_find_quarto_darwin_homebrew(monkeypatch):
    """On Darwin, returns the first existing candidate path."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("gui_system_check.shutil.which", lambda n: None)
    monkeypatch.setattr(
        "gui_system_check.os.path.exists",
        lambda p: p == "/opt/homebrew/bin/quarto",
    )
    assert gsc._find_quarto() == "/opt/homebrew/bin/quarto"


def test_find_quarto_darwin_applications(monkeypatch):
    """Falls back to /Applications/quarto/bin/quarto on Darwin."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("gui_system_check.shutil.which", lambda n: None)
    monkeypatch.setattr(
        "gui_system_check.os.path.exists",
        lambda p: p == "/Applications/quarto/bin/quarto",
    )
    assert gsc._find_quarto() == "/Applications/quarto/bin/quarto"


def test_find_quarto_not_found(monkeypatch):
    """Returns None when quarto is not on PATH and no fallback exists."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("gui_system_check.shutil.which", lambda n: None)
    monkeypatch.setattr("gui_system_check.os.path.exists", lambda p: False)
    assert gsc._find_quarto() is None


# ---------------------------------------------------------------------------
# _find_tlmgr
# ---------------------------------------------------------------------------


def test_find_tlmgr_found_on_path(monkeypatch):
    """Returns the PATH result when tlmgr is on PATH."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        "gui_system_check.shutil.which",
        lambda n: "/usr/bin/tlmgr" if n == "tlmgr" else None,
    )
    assert gsc._find_tlmgr() == "/usr/bin/tlmgr"


def test_find_tlmgr_darwin_tinytex(monkeypatch, tmp_path):
    """On Darwin finds tlmgr under ~/.TinyTeX/bin/universal-darwin/."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("gui_system_check.shutil.which", lambda n: None)
    tlmgr = tmp_path / ".TinyTeX" / "bin" / "universal-darwin" / "tlmgr"
    tlmgr.parent.mkdir(parents=True)
    tlmgr.touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "gui_system_check.os.path.exists",
        lambda p: Path(p) == tlmgr,
    )
    assert gsc._find_tlmgr() == str(tlmgr)


def test_find_tlmgr_linux_quarto_tools(monkeypatch, tmp_path):
    """On Linux finds tlmgr under ~/.local/share/quarto/tools/tinytex/."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("gui_system_check.shutil.which", lambda n: None)
    tlmgr = (
        tmp_path
        / ".local"
        / "share"
        / "quarto"
        / "tools"
        / "tinytex"
        / "bin"
        / "x86_64-linux"
        / "tlmgr"
    )
    tlmgr.parent.mkdir(parents=True)
    tlmgr.touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "gui_system_check.os.path.exists",
        lambda p: Path(p) == tlmgr,
    )
    assert gsc._find_tlmgr() == str(tlmgr)


def test_find_tlmgr_not_found(monkeypatch):
    """Returns None when tlmgr cannot be found anywhere."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("gui_system_check.shutil.which", lambda n: None)
    monkeypatch.setattr("gui_system_check.os.path.exists", lambda p: False)
    assert gsc._find_tlmgr() is None


# ---------------------------------------------------------------------------
# setup_status
# ---------------------------------------------------------------------------


def test_setup_status_complete_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("gui_system_check._setup_flag_dir", lambda: tmp_path)
    (tmp_path / "setup_complete.flag").write_text("PASS\n", encoding="utf-8")
    assert gsc.setup_status() == "complete_pass"


def test_setup_status_complete_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("gui_system_check._setup_flag_dir", lambda: tmp_path)
    (tmp_path / "setup_complete.flag").write_text("FAIL", encoding="utf-8")
    assert gsc.setup_status() == "complete_fail"


def test_setup_status_running(tmp_path, monkeypatch):
    """setup_running.flag present (no complete flag) → 'running'."""
    monkeypatch.setattr("gui_system_check._setup_flag_dir", lambda: tmp_path)
    (tmp_path / "setup_running.flag").write_text("1", encoding="utf-8")
    assert gsc.setup_status() == "running"


def test_setup_status_unknown(tmp_path, monkeypatch):
    """No flags at all → 'unknown'."""
    monkeypatch.setattr("gui_system_check._setup_flag_dir", lambda: tmp_path)
    assert gsc.setup_status() == "unknown"


def test_setup_status_oserror_returns_unknown(tmp_path, monkeypatch):
    """OSError reading flag file → falls through to 'unknown'."""
    monkeypatch.setattr("gui_system_check._setup_flag_dir", lambda: tmp_path)
    flag = tmp_path / "setup_complete.flag"
    flag.write_text("PASS", encoding="utf-8")
    # Replace the flag with a directory so read_text raises IsADirectoryError
    flag.unlink()
    flag.mkdir()
    assert gsc.setup_status() == "unknown"


# ---------------------------------------------------------------------------
# _r_lib_path
# ---------------------------------------------------------------------------


def test_r_lib_path_dev_mode_returns_none(monkeypatch):
    """In dev (non-frozen) mode, always returns None."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert gsc._r_lib_path() is None


def test_r_lib_path_frozen_dir_exists(monkeypatch, tmp_path):
    """In frozen mode, returns the r-library path when the directory exists."""
    lib = tmp_path / "r-library"
    lib.mkdir()
    fake_exe = tmp_path / "ResilenceScanReportBuilder-2"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    assert gsc._r_lib_path() == lib


def test_r_lib_path_frozen_dir_absent(monkeypatch, tmp_path):
    """In frozen mode, returns None when r-library does not exist."""
    fake_exe = tmp_path / "ResilenceScanReportBuilder-2"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    # r-library NOT created
    assert gsc._r_lib_path() is None

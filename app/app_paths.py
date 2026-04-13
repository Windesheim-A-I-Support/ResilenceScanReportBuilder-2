"""
Module-level path resolution and shared constants for ResilienceScan.

All functions and constants here are imported by app/main.py (via ``from
app.app_paths import *``) and by the mixin modules (via explicit imports).
Keeping them here avoids circular imports between main.py and the mixins.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from utils.constants import R_SUBPROCESS_TIMEOUT


# ---------------------------------------------------------------------------
# Path resolution — split into asset root (QMD + images, read-only) and
# data root (CSV, reports, logs — must be user-writable).
# ---------------------------------------------------------------------------
def _asset_root() -> Path:
    """Directory that contains ResilienceReport.qmd and companion assets.

    Dev:    repo root (one level up from app/)
    Frozen: sys._MEIPASS == _internal/ where --add-data extracts files
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    """User-writable directory for data/, reports/, and logs.

    Dev:    repo root (same as asset root, data files live alongside scripts)
    Frozen: APPDATA/ResilienceScan (Windows) or ~/.local/share/resiliencescan (Linux)
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", str(Path.home()))) / "ResilienceScan"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "ResilienceScan"
        return Path.home() / ".local" / "share" / "resiliencescan"
    return Path(__file__).resolve().parents[1]


def _default_output_dir() -> Path:
    """User-visible default folder for generated PDF reports.

    In the frozen app we place reports in Documents/ResilienceScanReports so
    they are easy for users to find.  AppData/Roaming is hidden by default on
    Windows and confuses users.  In dev mode we keep the repo reports/ folder.
    """
    if not getattr(sys, "frozen", False):
        return _data_root() / "reports"
    if sys.platform == "win32":
        docs = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
    else:
        docs = Path.home() / "Documents"
    if not docs.exists():
        docs = Path.home()
    return docs / "ResilienceScanReports"


def _sync_template() -> None:
    """Copy QMD and companion assets from _asset_root() to _data_root().

    In the frozen app the QMD lives in _internal/ (under Program Files) which
    is read-only for normal users.  Quarto always creates a .quarto/ scratch
    directory *next to the QMD file*, so it needs to be in a writable location.
    Copying to _data_root() (APPDATA/ResilienceScan) fixes this.

    In dev mode _asset_root() == _data_root() so no copy is needed.
    Only re-copies when the source QMD is newer than the destination (i.e. after
    an app update).
    """
    if not getattr(sys, "frozen", False):
        return
    src = _asset_root()
    dst = _data_root()
    dst.mkdir(parents=True, exist_ok=True)

    # Determine whether any QMD needs updating (use ResilienceReport as the sentinel)
    src_qmd = src / "ResilienceReport.qmd"
    dst_qmd = dst / "ResilienceReport.qmd"
    if (
        dst_qmd.exists()
        and src_qmd.exists()
        and src_qmd.stat().st_mtime <= dst_qmd.stat().st_mtime
    ):
        return  # already up-to-date

    # Copy all QMDs and shared assets
    for name in (
        "ResilienceReport.qmd",
        "SCROLReport.qmd",
        "references.bib",
        "QTDublinIrish.otf",
    ):
        s = src / name
        if s.exists():
            shutil.copy2(str(s), str(dst / name))
    for dname in ("img", "tex", "_extensions"):
        s = src / dname
        d = dst / dname
        if s.exists():
            if d.exists():
                shutil.rmtree(str(d))
            shutil.copytree(str(s), str(d))


def _config_path() -> Path:
    """Return path to config.yml in the writable user data directory."""
    return _data_root() / "config.yml"


def _r_library_path() -> "Path | None":
    """Return the bundled R library path when frozen, None in dev mode.

    The NSIS / postinst installer places R packages in an ``r-library``
    directory alongside the executable so the app uses them instead of (or
    in addition to) whatever the user has installed system-wide.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "r-library"
    return None


def _bundled_dir() -> "Path | None":
    """Return _internal/bundled/ when the app ships bundled R/Quarto/TinyTeX.

    Only present in macOS builds produced by the CI bundling steps.
    Returns None in dev mode or on Windows/Linux where dependencies are
    installed separately by the platform setup scripts.
    """
    if not getattr(sys, "frozen", False):
        return None
    d = Path(sys._MEIPASS) / "bundled"
    return d if d.exists() else None


def make_subprocess_env() -> dict:
    """Return an os.environ copy enriched with bundled tool paths.

    Centralises the environment setup that was previously duplicated across
    gui_generate.py and _check_r_packages_ready().  Safe to call on every
    platform and in dev mode — gracefully degrades to a plain copy of
    os.environ when no bundled tools exist.

    Sets (when bundled tools are present):
      PATH          — bundled Rscript / quarto / pdflatex prepended
      R_HOME        — bundled R.framework/Resources (macOS)
      R_LIBS        — bundled r-library prepended
      DYLD_FALLBACK_LIBRARY_PATH — bundled R dylib dir so Rscript loads
                                    even without a system-wide R install
    """
    env = os.environ.copy()
    extra_paths: list[str] = []

    bundled = _bundled_dir()
    if bundled:
        # ── Bundled R framework (macOS) ──────────────────────────────────
        r_resources = bundled / "R.framework" / "Resources"
        if r_resources.exists():
            env["R_HOME"] = str(r_resources)
            r_bin = r_resources / "bin"
            if r_bin.exists():
                extra_paths.append(str(r_bin))
            # Allow Rscript to load the R dylib even without system R:
            # Rscript has a hardcoded absolute dylib path; when that path
            # doesn't exist, dyld falls back to DYLD_FALLBACK_LIBRARY_PATH.
            r_fw_versions = bundled / "R.framework" / "Versions"
            if r_fw_versions.exists():
                ver_dirs = sorted(
                    d for d in r_fw_versions.iterdir()
                    if d.is_dir() and d.name != "Current"
                )
                if ver_dirs:
                    fallback = str(ver_dirs[-1])  # newest version dir
                    existing_fb = env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
                    env["DYLD_FALLBACK_LIBRARY_PATH"] = (
                        f"{fallback}{os.pathsep}{existing_fb}"
                        if existing_fb
                        else fallback
                    )

        # ── Bundled Quarto ───────────────────────────────────────────────
        quarto_bin = bundled / "quarto" / "bin"
        if quarto_bin.exists():
            extra_paths.append(str(quarto_bin))

        # ── Bundled TinyTeX ──────────────────────────────────────────────
        tinytex_bin_root = bundled / "tinytex" / "bin"
        if tinytex_bin_root.exists():
            arch_dirs = sorted(d for d in tinytex_bin_root.iterdir() if d.is_dir())
            if arch_dirs:
                extra_paths.append(str(arch_dirs[0]))

    # ── Bundled R packages (all platforms) ──────────────────────────────
    r_lib = _r_library_path()
    if r_lib is not None and r_lib.exists():
        existing = env.get("R_LIBS", "")
        env["R_LIBS"] = f"{r_lib}{os.pathsep}{existing}" if existing else str(r_lib)

    if extra_paths:
        env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + env.get("PATH", "")

    return env


def _check_r_packages_ready() -> "str | None":
    """Return None if all required R packages are findable, or an error string.

    Uses the same R_LIBS setup that the render subprocess uses, so this
    check is representative of what will happen during quarto render.
    Returns immediately (< 5 s) and is safe to call from any thread.
    """
    from gui_system_check import _R_PACKAGES, _find_rscript

    rscript = _find_rscript()
    if not rscript:
        return "Rscript not found on PATH"

    env = make_subprocess_env()

    pkg_list = ", ".join(f'"{p}"' for p in _R_PACKAGES)
    script = (
        f"pkgs <- c({pkg_list}); "
        "missing <- pkgs[!pkgs %in% rownames(installed.packages())];"
        "if (length(missing) == 0) cat('OK') "
        "else cat('MISSING:', paste(missing, collapse=', '))"
    )
    try:
        result = subprocess.run(
            [rscript, "-e", script],
            capture_output=True,
            text=True,
            timeout=R_SUBPROCESS_TIMEOUT,
            env=env,
        )
        out = (result.stdout + result.stderr).strip()
    except Exception as e:
        return f"R check error: {e}"

    if out.strip() == "OK":
        return None
    return out


# ---------------------------------------------------------------------------
# Computed module-level constants
# ---------------------------------------------------------------------------
ROOT_DIR = _asset_root()  # read-only assets (_internal/ when frozen)
_DATA_ROOT = _data_root()  # data/, reports/, logs — always writable
_sync_template()  # copy QMD + assets to _DATA_ROOT so quarto can write .quarto/ next to them
DATA_FILE = _DATA_ROOT / "data" / "cleaned_master.csv"
REPORTS_DIR = _DATA_ROOT / "reports"
DEFAULT_OUTPUT_DIR = _default_output_dir()  # user-visible reports folder
TEMPLATE = (
    _DATA_ROOT / "ResilienceReport.qmd"
)  # must be in writable _DATA_ROOT, not ROOT_DIR
LOG_FILE = _DATA_ROOT / "gui_log.txt"
CONFIG_FILE = _config_path()

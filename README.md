# ResilienceScan Report Builder

[![Latest Release](https://img.shields.io/github/v/release/Windesheim-A-I-Support/ResilenceScanReportBuilder-2?label=latest)](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/latest)

A Windows / Linux / macOS desktop application that generates personalised PDF resilience reports for survey respondents and distributes them by email.  Built with Python (Tkinter GUI) + R + Quarto + TinyTeX.

---

## Downloads

<!-- DOWNLOAD_LINKS_START -->
| Platform | Download |
|----------|----------|
| Windows | [Windows Installer (.exe)](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/download/v0.22.1/ResilenceScanReportBuilder-2-0.22.1-windows-setup.exe) |
| Windows | [Portable ZIP](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/download/v0.22.1/ResilenceScanReportBuilder-2-0.22.1-windows-portable.zip) |
| Linux | [.deb (Ubuntu/Debian)](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/download/v0.22.1/ResilenceScanReportBuilder-2-0.22.1-amd64.deb) |
| Linux | [AppImage](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/download/v0.22.1/ResilenceScanReportBuilder-2-0.22.1-x86_64.AppImage) |
| Linux | [Tarball (.tar.gz)](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/download/v0.22.1/ResilenceScanReportBuilder-2-0.22.1-linux-amd64.tar.gz) |
| macOS | [Tarball (.tar.gz, Apple Silicon)](https://github.com/Windesheim-A-I-Support/ResilenceScanReportBuilder-2/releases/download/v0.22.1/ResilenceScanReportBuilder-2-0.22.1-macos-arm64.tar.gz) |
<!-- DOWNLOAD_LINKS_END -->

> Download links update automatically with each release.

---

## Installation

### Windows

**Recommended: installer**

1. Download `*-windows-setup.exe`
2. Run it and follow the wizard (requires admin)
3. The installer copies the app to `C:\Program Files\ResilenceScanReportBuilder-2\` and immediately starts a background setup task (runs as SYSTEM) that downloads and installs R, Quarto, TinyTeX, and all R packages — no interaction needed
4. **Wait for setup to finish before launching the app** — typically 5–15 minutes on a normal connection.  Track progress in `C:\ProgramData\ResilienceScan\setup.log`; the last line should read `=== Dependency setup complete ===`
5. Launch from the desktop shortcut

**Alternative: portable ZIP**

1. Download `*-windows-portable.zip` and extract to any folder
2. Run `setup_dependencies.ps1` (right-click → Run with PowerShell) to install R/Quarto/TinyTeX manually, **or** install them yourself and ensure they are on `PATH`
3. Launch `ResilenceScanReportBuilder-2.exe`

**Setup log files (Windows)**

| File | Contents |
|------|----------|
| `C:\ProgramData\ResilienceScan\setup.log` | Step-by-step progress |
| `C:\ProgramData\ResilienceScan\setup_transcript.log` | Full stdout/stderr |
| `C:\ProgramData\ResilienceScan\setup_error.log` | Errors only |

---

### Linux

**Recommended: .deb package (Ubuntu / Debian)**

```bash
sudo dpkg -i ResilenceScanReportBuilder-2-0.22.1-amd64.deb
```

The `postinst` script launches `setup_linux.sh` in the background (via `nohup`) to install R, Quarto, TinyTeX, and R packages.  Progress is logged to `~/.local/share/ResilienceScan/setup.log`.

Launch once setup is complete:

```bash
ResilenceScanReportBuilder-2
# or from your app menu
```

**Alternative: AppImage (any Linux distro)**

```bash
chmod +x ResilenceScanReportBuilder-2-0.22.1-x86_64.AppImage
./ResilenceScanReportBuilder-2-0.22.1-x86_64.AppImage
```

You must install R, Quarto, and TinyTeX yourself and ensure they are on `PATH`.  Use the **Settings → Install Dependencies** button inside the app to run the automated setup script after first launch.

**Alternative: tarball**

```bash
tar -xzf ResilenceScanReportBuilder-2-0.22.1-linux-amd64.tar.gz
cd ResilenceScanReportBuilder-2
./ResilenceScanReportBuilder-2
```

Same dependency requirement as AppImage above.

---

### macOS (Apple Silicon)

The macOS build is **fully self-contained** — R 4.5.1, Quarto 1.6.39, TinyTeX, and all R packages are bundled inside the app.  No Homebrew, no CRAN installer, no manual setup required.

1. Download `*-macos-arm64.tar.gz`
2. Extract:
   ```bash
   tar -xzf ResilenceScanReportBuilder-2-0.22.1-macos-arm64.tar.gz
   ```
3. Move the extracted folder anywhere you like (e.g. `~/Applications/`)
4. Launch:
   ```bash
   cd ResilenceScanReportBuilder-2
   ./ResilenceScanReportBuilder-2
   ```
   Or double-click the executable in Finder.

> **macOS Gatekeeper note:** On first launch macOS may warn that the app is from an unidentified developer.  Right-click (or Control-click) the executable and choose **Open**, then confirm in the dialog.  You only need to do this once.

**Data directory (macOS):** `~/Library/Application Support/ResilienceScan/`

---

## First launch

On every platform the app runs a startup check:

1. R — `Rscript --version`
2. Quarto — `quarto --version`
3. TinyTeX / tlmgr — `tlmgr --version`
4. R packages — all 19 required packages

On **Windows and Linux** the check may fail immediately after installation if the background setup task has not finished yet.  Wait for setup to complete (see logs above) and relaunch.

On **macOS** all tools are bundled so the check should pass immediately.

If any check fails the app shows a dialog listing what is missing.  Use **Settings → Install Dependencies** to re-run the setup script.

---

## Configuration

### SMTP / email

Open the **Email → Configuration** tab and fill in your SMTP server, port, username, and password.  The password is stored in the OS keyring (not in a plain-text file).

Config file locations (for manual editing):

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\ResilienceScan\config.yml` |
| Linux | `~/.local/share/resiliencescan/config.yml` |
| macOS | `~/Library/Application Support/ResilienceScan/config.yml` |

On Windows the app tries Outlook COM first and falls back to SMTP.  On Linux and macOS only SMTP is used.

### Output folder

By default reports are saved to:

| Platform | Default path |
|----------|-------------|
| Windows | `Documents\ResilienceScanReports\` |
| Linux / macOS | `~/Documents/ResilienceScanReports/` |

Change it in the **Settings** tab at any time.

---

## What it does

1. **Import** — reads respondent data from `.xlsx`, `.xlsm`, `.xls`, `.ods`, `.xml`, `.json`, `.jsonl`, `.csv`, or `.tsv` and upserts into a clean master CSV
2. **Generate** — renders one PDF per respondent via `quarto render ResilienceReport.qmd` (R + LaTeX/TikZ pipeline)
3. **Validate** — checks every generated PDF against the source CSV values
4. **Send** — emails each PDF to the right recipient; tracks send status per respondent across sessions so re-runs only send to people who haven't received their report yet

---

## Troubleshooting

### Windows: app won't start after fresh install

The background setup task is still running.  Check `C:\ProgramData\ResilienceScan\setup.log` — wait until the last line is `=== Dependency setup complete ===` (typically 5–15 minutes).

If setup is complete but the startup check still fails, log out and back in so Explorer inherits the updated `PATH`.

### Linux: R packages not found

The app sets `R_LIBS` to `<InstallDir>/r-library` for all subprocesses.  If packages are still missing, check that `setup_linux.sh` completed without errors (look for errors in `~/.local/share/ResilienceScan/setup.log`).  Re-run via **Settings → Install Dependencies**.

### macOS: "cannot be opened because the developer cannot be verified"

Right-click (Control-click) the executable → **Open** → **Open** in the confirmation dialog.  This one-time step bypasses Gatekeeper for unsigned apps.

### macOS: app opens then immediately closes

Check that you extracted the full tarball — the app requires its sibling `r-library/` directory (R packages) and `_internal/` directory (bundled R/Quarto/TinyTeX) to be present next to the executable.

### `quarto render` fails

`ResilienceReport.qmd` depends on the companion assets bundled in `_internal/` (LaTeX extensions, images, fonts, bibliography).  On frozen/installed builds the app copies these to the data directory at startup.  If render fails, try relaunching the app to re-trigger the sync.

### SMTP email not sending

Verify credentials in **Email → Configuration**.  Common issues: wrong port (use 587 for STARTTLS, 465 for SSL), app password required for accounts with 2FA (e.g. Microsoft 365).

---

## Development setup

```bash
# Python environment
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

pip install -r requirements.txt
pip install pytest ruff pyyaml PyPDF2   # dev tools

# Prerequisites (dev only — not needed for the bundled macOS app)
# - R >= 4.4 with all 19 R packages
# - Quarto >= 1.6
# - TinyTeX:  quarto install tinytex

# Run the GUI
python app/main.py

# Run pipeline steps individually
python clean_data.py              # clean data/cleaned_master.csv in-place
python generate_all_reports.py    # render one PDF per row → reports/
python validate_reports.py        # validate PDFs against CSV values
python send_email.py              # send PDFs (TEST_MODE=True by default)

# Lint + test (mirrors CI)
ruff check .
ruff format --check .
pytest
```

---

## Release workflow

```bash
# Bump version in pyproject.toml, then push to main
git add pyproject.toml && git commit -m "chore: bump to v0.X.Y"
git push origin main
```

CI detects that no git tag `v<version>` exists, builds Windows / Linux / macOS artifacts, publishes the GitHub Release, and updates the download links in this README automatically.  **Do not create tags manually.**

---

## Architecture

```
app/main.py                     ← Tkinter GUI (entry point + PyInstaller target)
app/
  ├── gui_data.py               ← Data tab, CSV load/convert, quality analysis
  ├── gui_generate.py           ← Generation tab, PDF render, cancel
  ├── gui_email.py              ← Email tabs, tracker display
  ├── gui_settings.py           ← Settings tab, system check, OS-specific setup
  ├── gui_logs.py               ← Logs tab
  ├── app_paths.py              ← All path constants + make_subprocess_env()
  └── _version.py               ← Injected by CI
utils/
  ├── path_utils.py             ← get_user_base_dir() (platform-specific)
  ├── filename_utils.py         ← safe_filename(), safe_display_name()
  └── constants.py              ← SCORE_COLUMNS, REQUIRED_COLUMNS, timeouts
gui_system_check.py             ← Runtime R / Quarto / TinyTeX checks
email_tracker.py                ← Per-recipient send-status JSON store
update_checker.py               ← Background GitHub release check
ResilienceReport.qmd            ← Quarto/R/LaTeX report template
SCROLReport.qmd                 ← SCROL matrix report template
packaging/
  ├── setup_dependencies.ps1   ← Windows: installs R/Quarto/TinyTeX as SYSTEM
  ├── launch_setup.ps1         ← Windows: Task Scheduler launcher
  ├── setup_linux.sh           ← Linux: installs R/Quarto/TinyTeX
  ├── setup_macos.sh           ← macOS: Homebrew-based fallback setup
  └── postinst.sh              ← .deb postinst (deferred setup_linux.sh)
```

### Bundled macOS structure (inside the tarball)

```
ResilenceScanReportBuilder-2/
├── ResilenceScanReportBuilder-2    ← executable
├── r-library/                      ← R packages (writable)
└── _internal/
    ├── bundled/
    │   ├── R.framework/            ← R 4.5.1 (CRAN, arm64)
    │   ├── quarto/                 ← Quarto 1.6.39
    │   └── tinytex/                ← TinyTeX with tlmgr
    └── [PyInstaller dependencies]
```

---

## CI workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push / PR to main | lint, test, build (Windows + Linux + macOS), publish release |
| `codeql.yml` | push / PR / weekly | security analysis |
| `platform.yml` | push to main | cross-platform smoke tests |

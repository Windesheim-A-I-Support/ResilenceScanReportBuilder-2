# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the GUI (main application)
python app/main.py

# Run pipeline steps individually
python clean_data.py                 # clean data/cleaned_master.csv in-place
python generate_all_reports.py       # render one PDF per row → reports/
python validate_reports.py           # validate generated PDFs against CSV values
python send_email.py                 # send PDFs (TEST_MODE=True by default)

# Lint and test (CI)
pip install pytest ruff pyyaml PyPDF2
ruff check .
ruff format --check .
pytest
pytest tests/test_smoke.py::test_import_main_module   # single test
pytest tests/test_pipeline_sample.py                  # anonymised fixture tests

# Regenerate the anonymised test fixture
python scripts/make_sample_data.py
```

## Release workflow

Bump `version` in `pyproject.toml` and push to `main`. CI detects no git tag `v<version>` exists and fires the build matrix. Do **not** create tags manually. macOS is not a target — only Windows and Linux matter.

---

## Architecture

`app/main.py` is the canonical entry point (Tkinter GUI + PyInstaller target).

```
app/main.py
  ├── imports convert_data          → Excel/ODS/XML/CSV/TSV → data/cleaned_master.csv
  ├── imports clean_data            → cleans and validates CSV in-place
  ├── imports email_tracker         → tracks per-recipient send status
  ├── imports gui_system_check      → verifies R/Quarto/TinyTeX are present at runtime
  ├── imports update_checker        → background GitHub release check
  └── imports dependency_manager    → stub (installation handled by the installer)
```

### Path resolution (frozen vs dev)

| Variable | Dev | Frozen (installed) |
|----------|-----|--------------------|
| `ROOT_DIR` / `_asset_root()` | repo root | `sys._MEIPASS` (`_internal/`) |
| `_DATA_ROOT` / `_data_root()` | repo root | `%APPDATA%\ResilienceScan` / `~/.local/share/resiliencescan` |
| `DATA_FILE` | `repo/data/cleaned_master.csv` | `APPDATA/data/cleaned_master.csv` |
| `REPORTS_DIR` | `repo/reports/` | `APPDATA/reports/` (temp write location only) |
| `DEFAULT_OUTPUT_DIR` | `repo/reports/` | `Documents\ResilienceScanReports\` |
| `TEMPLATE` | `repo/ResilienceReport.qmd` | `APPDATA/ResilienceScan/ResilienceReport.qmd` (copied from `_internal/` by `_sync_template()`) |

**Rule:** Any code that reads or displays reports must use `Path(self.output_folder_var.get())`, never `REPORTS_DIR`.

---

## Pipeline flow

```
data/*.xlsx  (or .xls, .ods, .xml, .tsv, .csv)
     │ convert_data.py
     ▼
data/cleaned_master.csv
     │ clean_data.py
     ▼
data/cleaned_master.csv  [validated & cleaned]
     │ generate_all_reports.py + ResilienceReport.qmd  (calls quarto render)
     ▼
reports/YYYYMMDD ResilienceScanReport (Company - Person).pdf
     │ validate_reports.py
     ▼
     │ send_email.py
     ▼
emails via Outlook COM (Windows) or SMTP fallback (Office365)
```

**Key data file:** `data/cleaned_master.csv`
**Score columns:** `up__r/c/f/v/a`, `in__r/c/f/v/a`, `do__r/c/f/v/a` — range 0–5
**PDF naming:** `YYYYMMDD ResilienceScanReport (Company Name - Firstname Lastname).pdf`

---

## Packaging strategy

**Staged installer** — the installer silently downloads and sets up all dependencies (R, Quarto, TinyTeX, R packages) during installation.

`ResilienceReport.qmd` is deeply LaTeX-dependent (TikZ, kableExtra, custom titlepage extension, custom fonts, raw `.tex` includes). The PDF engine **cannot** be switched to Typst or WeasyPrint — TinyTeX is required.

### Pinned dependency versions

| Dependency | Version | Notes |
|------------|---------|-------|
| R | 4.5.1 (pinned) | SYSTEM account has no network at install time; no auto-discovery |
| Quarto | 1.6.39 | GitHub releases |
| TinyTeX | Quarto-pinned | `quarto install tinytex` |
| Python | ≥ 3.11 | bundled by PyInstaller |

### R packages

`readr`, `dplyr`, `stringr`, `tidyr`, `ggplot2`, `knitr`, `fmsb`, `scales`, `viridis`, `patchwork`, `RColorBrewer`, `gridExtra`, `png`, `lubridate`, `kableExtra`, `rmarkdown`, `jsonlite`, `ggrepel`, `cowplot`

### LaTeX packages (tlmgr names)

`pgf`, `xcolor`, `colortbl`, `booktabs`, `multirow`, `float`, `wrapfig`, `pdflscape`, `geometry`, `preprint`, `graphics`, `tabu`, `threeparttable`, `threeparttablex`, `ulem`, `makecell`, `environ`, `trimspaces`, `caption`, `hyperref`, `setspace`, `fancyhdr`, `microtype`, `lm`, `needspace`, `varwidth`, `mdwtools`, `xstring`, `tools`

**Note:** `capt-of` is NOT installed via tlmgr (tar extraction fails on fresh TinyTeX). A minimal `capt-of.sty` stub is written directly by `setup_dependencies.ps1` / `setup_linux.sh` and registered with `mktexlsr`.

---

## Working rule

**Do not start the next milestone until the current one is fully verified by its gate condition.** Each gate must pass on a clean run before any work on the next milestone begins.

---

## Completed milestones

| Milestone | Description | Version |
|---|---|---|
| M1 | Fix CI, ship real app | v0.13.0 |
| M2 | Fix paths, consolidate cleaners | v0.14.0 |
| M3 | Implement data conversion | v0.15.0 |
| M4 | End-to-end report generation | v0.16.0 |
| M5 | Fix validation + email tracker | v0.17.0 |
| M6 | Email sending | v0.18.0 |
| M7 | Startup system check guard | v0.19.0 |
| M8 | Complete installer: R + Quarto + TinyTeX | v0.20.5 |
| M9 | Fix Windows installer: R path, LaTeX packages, capt-of | v0.20.14 |
| M10 | Fix report generation in installed app (frozen path split) | v0.21.0 |
| M11 | Anonymised sample dataset + pipeline smoke tests | v0.21.0 |
| M12 | End-to-end CI pipeline test (e2e.yml) | v0.21.0 |
| M13 | In-app update checker | v0.21.0 |
| M14 | README download badges + CI auto-update | v0.21.0 |
| M15 | Fix frozen app render failures (.quarto/ PermissionDenied, TinyTeX Quarto 1.4+, R_LIBS) | v0.21.4–v0.21.7 |
| M16 | Cross-platform test runner (platform.yml — Ubuntu + Windows on every push) | v0.21.14 |
| M17 | e2e CI passes on both platforms | v0.21.17 |
| M18 | Installer/version consistency tests; setup_linux.sh ASCII fix | v0.21.18 |
| M19 | Windows real-machine testing (Write-Log order, R pin, _version.py, output folder, cancel race, email folder) | v0.21.19–v0.21.25 |
| M20 | Setup completion feedback (sentinel flags, in-app polling, desktop notifications) | v0.21.26 |
| M21 | Fix email sending (thread-safe logging, send_config dict, except handler, tracker display) | v0.21.27 |
| M22 | R installer hardening + multi-format import (ODS/XML/CSV/TSV) | v0.21.28–v0.21.29 |
| M24 | Independent code analysis → `REVIEW.md` (27 findings) | v0.21.29 |
| M23 | SCROL matrix report template (`SCROLReport.qmd`); template dropdown; `_sync_template()` copies both QMDs | v0.21.30 |
| M25 | Thread-safety: `threading.Event` cancel, `threading.Lock` proc guard, all widget updates via `root.after(0,…)` | v0.21.31 |
| M26 | Frozen-app path fixes: `view_cleaning_report` uses `_DATA_ROOT`; `generate_executive_dashboard` removed (M27) | v0.21.31 |
| M27 | Dead-code removal: `generate_executive_dashboard()` + toolbar button deleted | v0.21.31 |
| M28 | Error handling: specific SMTP exceptions, SMTP port validation, temp PDF `finally` cleanup, debug logging in update_checker | v0.21.31 |
| M29 | Security: `TEST_EMAIL` → `test@example.com` default (env var override); SMTP timeout=30 | v0.21.31 |
| M30 | Extract shared utilities: `utils/path_utils`, `utils/filename_utils`, `utils/constants`; wire into 6 files | v0.21.36 |
| M31 | Test coverage: `test_frozen_paths.py` (6), `test_csv_validation.py` (11), `test_shared_utils.py` (26), `test_email_send.py` (13), `test_thread_safety.py` (13) | v0.21.36 |
| M32 | Refactor `app/main.py` → 224 lines; 5 mixin modules (`gui_data`, `gui_generate`, `gui_email`, `gui_settings`, `gui_logs`); ruff suppression removed | v0.21.36 |
| M33 | Encoding safety — `encoding="utf-8"` on all text `open()` calls in pipeline + app files | v0.21.36 |
| M34 | Output folder writability validation: `_validate_output_folder()` called before generation starts | v0.21.38 |
| M35 | Log format standardisation in pipeline scripts — all prints use `{INFO,WARN,ERROR,OK}` | v0.21.39 |
| — | Installer hardening: `requireNamespace()` package checks; r-library ACL fix; `requirements_check.log` version validation | v0.21.37 |
| — | Installer bug-fixes from real-world test: Rscript version regex; pre-flight skip; SID-based ACLs; tlmgr self-update; Linux SETUP_RESULT; CODENAME fallback | v0.21.40 |
| — | Round-2 independent code review → `REVIEW2.md` (19 findings) | v0.21.40 |
| — | `launch_setup.ps1` blocks NSIS until `setup_complete.flag` written (installer now shows "Complete" only after R/Quarto/TinyTeX installed) | v0.21.41 |
| M36 | Frozen-app path fixes: `email_template.json` → `_DATA_ROOT`; `integrity_validation_report.*` → `_DATA_ROOT / data` | v0.21.41 |
| M37 | Thread-safety: all widget writes in `generate_reports_thread()` via `root.after`; duplicate `except Exception` removed; `self.df` snapshot for email thread; `finalize()` None guard | v0.21.41 |
| M38 | Error handling: `yaml is None` guard; port cast guards; SMTP `timeout=30`; `try/finally` SMTP close; specific SMTP exceptions; temp PDF `finally` in single-report worker | v0.21.41 |
| M39 | Dead code: `use_outlook` + unreachable else SMTP block removed; local `safe_filename`/`safe_display_name` in `gui_generate.py` replaced with `utils.filename_utils` import; `update_time`/`show_about` moved to `main.py`; `pd.read_csv`/`to_csv` + `encoding="utf-8"` | v0.21.41 |
| M40 | Test coverage: `test_frozen_paths.py` `_sync_template()` (4 new); `test_app_paths.py` `_check_r_packages_ready()` (5 new); `test_email_send.py` auth-error assertion tightened | v0.21.41 |
| M41 | Security: `priority_accounts` hardcoded emails moved to `config.yml` `outlook_accounts` key; `setup_linux.sh` Rscript guard + stderr-to-log | v0.21.41 |
| M42 | Installer: `launch_setup.ps1` deletes stale `setup_complete.flag` before starting task; NSIS checks exit code and shows error dialog on FAIL | v0.21.42 |

**Current version: v0.21.42 — 210 tests, ruff clean**

---

## Active milestones

All milestones M1–M42 complete. No active milestones.

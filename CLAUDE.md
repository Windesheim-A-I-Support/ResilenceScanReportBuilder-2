# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Commands

```bash
# Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the GUI
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

# Regenerate anonymised test fixture
python scripts/make_sample_data.py
```

## Release workflow

Bump `version` in `pyproject.toml` and push to `main`. CI detects no git tag `v<version>` and fires the build matrix. **Do not create tags manually.** macOS is not a target — only Windows and Linux.

---

## Architecture

`app/main.py` is the entry point (Tkinter GUI + PyInstaller target, 255 lines). It inherits from five mixins:

| Mixin | File | Responsibility |
|---|---|---|
| `DataMixin` | `app/gui_data.py` | Data tab, CSV load/convert, quality analysis |
| `GenerationMixin` | `app/gui_generate.py` | Generation tab, PDF render, thread-safe cancel |
| `EmailMixin` | `app/gui_email.py` | Email tabs, SMTP send, template editor |
| `SettingsMixin` | `app/gui_settings.py` | Startup guard, system check, installer |
| `LogsMixin` | `app/gui_logs.py` | Logs tab, log/log_gen/log_email helpers |

Shared infrastructure:

| Module | Purpose |
|---|---|
| `app/app_paths.py` | All path constants + `_sync_template()`, `_check_r_packages_ready()` |
| `utils/path_utils.py` | `get_user_base_dir()` for pipeline scripts |
| `utils/filename_utils.py` | `safe_filename()`, `safe_display_name()` |
| `utils/constants.py` | `SCORE_COLUMNS`, `REQUIRED_COLUMNS` |
| `gui_system_check.py` | R / Quarto / TinyTeX runtime checks |
| `email_tracker.py` | Per-recipient send-status JSON store |
| `update_checker.py` | Background GitHub release check |

### Path resolution (frozen vs dev)

| Constant | Dev | Frozen (installed) |
|---|---|---|
| `ROOT_DIR` / `_asset_root()` | repo root | `sys._MEIPASS` (`_internal/`) — **read-only** |
| `_DATA_ROOT` / `_data_root()` | repo root | `%APPDATA%\ResilienceScan` (Win) / `~/.local/share/resiliencescan` (Linux) |
| `DATA_FILE` | `repo/data/cleaned_master.csv` | `APPDATA/data/cleaned_master.csv` |
| `REPORTS_DIR` | `repo/reports/` | `APPDATA/reports/` — temp write location only |
| `DEFAULT_OUTPUT_DIR` | `repo/reports/` | `Documents\ResilienceScanReports\` |

**Rule:** Code that reads or displays reports must use `Path(self.output_folder_var.get())`, never `REPORTS_DIR`.

`_sync_template()` runs at import time and copies QMDs + assets from `_asset_root()` to `_data_root()` so Quarto can write `.quarto/` next to them (frozen `_internal/` is read-only).

---

## Pipeline flow

```
data/*.xlsx / .xlsm / .xls (incl. SpreadsheetML) / .ods / .xml / .json / .jsonl / .csv / .tsv
     │ convert_data.py  — reads → normalises columns → upserts into cleaned_master.csv
     ▼                    (new records first; reportsent preserved for existing rows)
data/cleaned_master.csv
     │ clean_data.py
     ▼
data/cleaned_master.csv  [validated & cleaned]
     │ generate_all_reports.py + ResilienceReport.qmd or SCROLReport.qmd
     ▼
reports/YYYYMMDD <TemplateName> (Company Name - Firstname Lastname).pdf
     │ validate_reports.py
     │ send_email.py
     ▼
emails via Outlook COM (Windows) or SMTP fallback (Office365)
```

**Key data file:** `data/cleaned_master.csv`
**Score columns:** `up__r/c/f/v/a`, `in__r/c/f/v/a`, `do__r/c/f/v/a` — range 0–5
**PDF naming:** `YYYYMMDD <TemplateName> (Company Name - Firstname Lastname).pdf`

---

## Packaging strategy

**Staged installer** — NSIS (Windows) / postinst (Linux) silently downloads and installs R, Quarto, TinyTeX, and R packages during installation. Python is bundled by PyInstaller (`--onedir`).

`ResilienceReport.qmd` and `SCROLReport.qmd` are deeply LaTeX-dependent (TikZ, kableExtra, custom titlepage extension, custom fonts, raw `.tex` includes). **The PDF engine cannot be switched to Typst or WeasyPrint** — TinyTeX is required.

**Do not modify `.qmd` templates** — they contain interdependent LaTeX/R/Quarto logic that is fragile to whitespace and encoding changes.

### Pinned dependency versions

| Dependency | Version | Notes |
|---|---|---|
| R | 4.5.1 | Pinned — SYSTEM account has no network at install time |
| Quarto | 1.6.39 | GitHub releases |
| TinyTeX | Quarto-pinned | `quarto install tinytex` |
| Python | ≥ 3.11 | Bundled by PyInstaller |

### R packages

`readr`, `dplyr`, `stringr`, `tidyr`, `ggplot2`, `knitr`, `fmsb`, `scales`, `viridis`, `patchwork`, `RColorBrewer`, `gridExtra`, `png`, `lubridate`, `kableExtra`, `rmarkdown`, `jsonlite`, `ggrepel`, `cowplot`

### LaTeX packages (tlmgr)

`pgf`, `xcolor`, `colortbl`, `booktabs`, `multirow`, `float`, `wrapfig`, `pdflscape`, `geometry`, `preprint`, `graphics`, `tabu`, `threeparttable`, `threeparttablex`, `ulem`, `makecell`, `environ`, `trimspaces`, `caption`, `hyperref`, `setspace`, `fancyhdr`, `microtype`, `lm`, `needspace`, `varwidth`, `mdwtools`, `xstring`, `tools`

**Note:** `capt-of` is NOT installed via tlmgr — a minimal stub is written by the installer scripts directly and registered with `mktexlsr`.

---

## Working rule

**Do not start the next milestone until the current one is fully verified by its gate condition.**

---

## Milestone history (summary)

| Range | What was built |
|---|---|
| M1–M7 | Core app: CI, paths, data conversion, report generation, email, startup guard |
| M8–M9 | Windows installer (R, Quarto, TinyTeX, LaTeX packages, capt-of) |
| M10–M14 | Frozen-app path split, smoke tests, e2e CI, update checker, README badges |
| M15–M19 | Frozen-app render fixes, cross-platform CI, Windows real-machine testing |
| M20–M23 | Setup completion feedback, email fixes, R hardening, SCROL template |
| M24 | Independent code review → REVIEW.md (27 findings) |
| M25–M29 | Thread-safety, frozen paths, dead-code removal, error handling, security |
| M30–M35 | Shared utils extraction, test coverage (69 tests), main.py refactor to 5 mixins, encoding safety, output folder validation, log standardisation |
| M36–M41 | Round-2 review fixes: path correctness, thread-safety, error handling, dead code, test coverage, security |
| M42–M45 | Installer hardening: stale-flag cleanup, smoke test CI, R repair in-app |
| M46 | SpreadsheetML XLS support + upsert (new records first, reportsent preserved) |
| M47 | JSON / JSONL / XLSM format support; dummy fixtures in tests/fixtures/ |
| M48 | Non-GUI quick wins: encoding fix, dead code, constants, pandas removal from filename_utils |
| M49 | GUI improvements: dead if/else, score constant, SMTP/Quarto timeout constants, silent log fix |
| M50 | Module splitting: gui_email.py → template+send+tracker; gui_data.py → QualityMixin extracted |
| M51 | Exception narrowing in pipeline scripts; type hints on gui_system_check.py functions |

| M52 | Thread safety + resource leaks (REVIEW4.md 1.1, 1.2, 1.3, 2.1, 4.1) |
| M53 | Security: keyring credential storage (REVIEW4.md 3.1) |
| M54 | Code quality quick wins (REVIEW4.md 5.1, 5.2, 5.3) |
| M55 | GUI audit: remove dead buttons (data_quality_dashboard.py / clean_data_enhanced.py missing); consolidate redundant controls |
| M56 | GUI visual upgrade: modern ttk theme, improved layout, spacing, typography |
| M57 | Email sender configuration: per-send "From" address selection, multiple sender profiles |

**Current version: v0.21.51 — 268 tests, ruff clean**

---

## Active milestones

### M52 — Thread safety + resource leaks

| Task | Finding | File | Fix |
|---|---|---|---|
| T1 | 1.1 | gui_quality.py:120–139, 167–191 | Wrap all widget/messagebox calls in `root.after(0, ...)` |
| T2 | 1.2 | email_tracker.py | Add `threading.Lock`; acquire in every method touching `_recipients` or `_save()` |
| T3 | 1.3 | gui_logs.py:63–67 | Add module-level `_LOG_LOCK`; acquire around file write |
| T4 | 2.1 | gui_email_send.py:739–741 | Wrap `server.quit()` in `try/except`; call `server.close()` on failure |
| T5 | 4.1 | convert_data.py:152, 160 | Use `with pd.ExcelFile(...) as xl:` context manager in `_read_xls` and `_read_ods` |

Gate: `ruff check .` clean, `pytest` 268+ pass, no new warnings.

### M53 — Security: keyring credential storage

| Task | Finding | File | Fix |
|---|---|---|---|
| T1 | 3.1 | gui_email_template.py:226, 257–258 | Replace plaintext password in config.yml with `keyring`; migrate on first load |

Gate: password absent from `config.yml`; save/load round-trip works on Linux and Windows.

### M54 — Code quality quick wins

| Task | Finding | File | Fix |
|---|---|---|---|
| T1 | 5.1 | gui_email_send.py:461–479 | Extract `_find_row(df, company, person) → Series \| None` helper |
| T2 | 5.2 | convert_data.py:128–130 | `_cell_text` returns `""` not `None` |
| T3 | 5.3 | gui_email_send.py:~824 | Add `TEST_MODE_LABEL` to `utils/constants.py` |

Gate: `ruff check .` clean, `pytest` 268+ pass.

### M55 — GUI audit: remove dead controls

The GUI audit (2026-03-19) confirmed all 41+ buttons are implemented, but two
buttons in `gui_quality.py` invoke scripts that do not exist in the repo:

| Task | File | Issue | Fix |
|---|---|---|---|
| T1 | gui_quality.py:112 | "Run Quality Dashboard" calls `data_quality_dashboard.py` — missing | Remove button and `run_quality_dashboard()` method, or implement the script |
| T2 | gui_quality.py:160 | "Run Data Cleaner" calls `clean_data_enhanced.py` — missing | Remove button and `run_data_cleaner()` method, or implement the script |
| T3 | gui_quality.py / gui_data.py | Remove `QualityMixin` if all its public methods are removed | Clean up mixin wiring in main.py if needed |

Decision: **remove** both buttons/methods (scripts do not exist and are not planned).
If the scripts are added later, the buttons can be re-introduced.

Gate: `ruff check .` clean, `pytest` 268+ pass, no dead imports.

### M56 — GUI visual upgrade

Replace the default Tk appearance with a modern, consistent look.

| Task | Details |
|---|---|
| T1 | Add `sv-ttk` (Sun Valley theme) or `ttkthemes` to `requirements.txt` and apply at startup |
| T2 | Standardise padding/spacing across all tabs (consistent `padx`/`pady`) |
| T3 | Improve typography: use a single readable font throughout, not mixed `Courier`/default |
| T4 | Improve progress bars, labels, and button sizing for visual hierarchy |
| T5 | Dashboard tab: card-style status widgets instead of plain labels |

Gate: App launches, all existing tests pass, visual review on both Linux and Windows.

### M57 — Email sender configuration

Allow the user to choose which email address to send from before starting a send run.

| Task | Details |
|---|---|
| T1 | Add a "From address" dropdown/entry to the Email Send tab, pre-filled from SMTP config |
| T2 | Support multiple named sender profiles in `config.yml` (e.g. "School A", "School B") with different `from_address`/`username`/`password` |
| T3 | Selected profile is passed through to `_send_emails_impl` and used for both Outlook (set sender) and SMTP (`From:` header) |
| T4 | Profile management UI in the Email Template tab: add / rename / delete profiles |
| T5 | Keyring stores password per profile (after M53) |

Gate: Can configure ≥2 profiles, switch between them in the Send tab, and emails reflect the correct From address.

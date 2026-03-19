# REVIEW4.md — Round 4 Code Review

Date: 2026-03-19
Version reviewed: v0.21.51 (268 tests, ruff clean)
Scope: All Python source files (app/, utils/, pipeline scripts, email_tracker.py, gui_system_check.py)

---

## Summary table

| ID  | File : line(s)                        | Severity | Description                                        |
|-----|---------------------------------------|----------|----------------------------------------------------|
| 1.1 | gui_quality.py : 120–139, 167–191     | High     | Tkinter widgets updated directly from background thread |
| 1.2 | email_tracker.py : throughout         | Medium   | `_recipients` dict accessed without a threading lock |
| 1.3 | gui_logs.py : 63–67                   | Medium   | Log file write not protected by a lock — interleaving possible |
| 2.1 | gui_email_send.py : 739–741           | Medium   | `server.quit()` in `finally` may itself raise and leak the socket |
| 3.1 | gui_email_template.py : 226, 257–258  | High     | SMTP password persisted to and read from plaintext `config.yml` |
| 4.1 | convert_data.py : 152, 160            | High     | `pd.ExcelFile` not closed — file-handle leak on exception |
| 5.1 | gui_email_send.py : 461–479           | Medium   | DataFrame row-lookup duplicated; extract helper        |
| 5.2 | convert_data.py : 128–130             | Low      | `_cell_text()` returns `None` for empty cells; callers get `None` silently |
| 5.3 | gui_email_send.py : ~824              | Low      | `"[TEST MODE]"` hard-coded literal; should be a constant |

---

## Detailed findings

### 1.1 — Tkinter thread safety: gui_quality.py

**Severity:** High
**Files:** `app/gui_quality.py` lines 120–139, 167–191

Both `run_quality_dashboard` and `run_data_cleaner` spawn a daemon thread
(`run_in_thread`) that directly manipulates Tkinter widgets:

```python
# run_in_thread — background thread
self.quality_text.delete("1.0", tk.END)   # direct widget write
self.quality_text.insert("1.0", result.stdout)
messagebox.showinfo(...)                   # dialog from thread
self.load_initial_data()                   # triggers more GUI updates
```

Tkinter is not thread-safe. Calling widget methods or `messagebox` from any
thread other than the main thread causes undefined behaviour (crashes,
corruption, silent failures) — especially on Windows.

**Fix:** Schedule all GUI updates via `self.root.after(0, callback)`.

---

### 1.2 — EmailTracker: no threading lock

**Severity:** Medium
**File:** `email_tracker.py` throughout

`EmailTracker._recipients` (a plain `dict`) is read and written from both the
email-send background thread (`mark_sent`, `mark_pending`) and the main GUI
thread (`get_status`, `get_all_statuses`). There is no lock. Python's GIL
does not protect composite read-modify-write operations, and `_save()` writes
to disk inside the same unprotected method.

**Fix:** Add a `threading.Lock` to `__init__` and acquire it in every public
method that touches `_recipients` or calls `_save()`.

---

### 1.3 — Log file writes not protected by a lock

**Severity:** Medium
**File:** `app/gui_logs.py` lines 63–67

```python
# comment says "thread-safe" but the file open is unguarded
with open(LOG_FILE, "a", encoding="utf-8") as f:
    f.write(log_message)
```

`log()` is called from generation and email threads simultaneously. Without a
lock, concurrent `open/write/close` cycles on the same file can interleave,
producing garbled lines (especially on Windows where file locking is strict and
may also raise `PermissionError`).

**Fix:** Add a module-level `threading.Lock` and acquire it around the file
write. The GUI-update path already uses `root.after()` correctly.

---

### 2.1 — SMTP socket may leak if `server.quit()` raises

**Severity:** Medium
**File:** `app/gui_email_send.py` lines 739–741

```python
try:
    server.starttls()
    server.login(...)
    server.send_message(msg)
finally:
    server.quit()   # if starttls/login already dropped the connection,
                    # quit() raises SMTPServerDisconnected and the
                    # TCP socket is never closed
```

If `starttls()` or `login()` fails and leaves the connection in a bad state,
`server.quit()` throws `SMTPServerDisconnected`. The exception propagates out
of the `finally` block and the underlying socket is never closed (until GC, which
on Windows may keep the port open for minutes).

**Fix:**
```python
finally:
    try:
        server.quit()
    except Exception:
        server.close()
```

---

### 3.1 — SMTP password persisted in plaintext `config.yml`

**Severity:** High
**File:** `app/gui_email_template.py` lines 226, 257–258

```python
data = {
    "smtp": {
        ...
        "password": self.smtp_password_var.get(),   # plaintext
    }
}
CONFIG_FILE.write_text(yaml.dump(data, ...), encoding="utf-8")
```

`config.yml` is stored in `_DATA_ROOT` (user's home or `APPDATA`), readable
by any process running as that user. On a shared or compromised machine this
exposes SMTP credentials.

**Fix:** Use the `keyring` library to store and retrieve the password via the OS
credential store (Windows Credential Manager / Linux Secret Service / macOS
Keychain). Store only non-sensitive SMTP settings in `config.yml`; omit the
`password` key entirely. Add `keyring` to `requirements.txt`.

Migration: on first load, if a password exists in `config.yml`, migrate it to
keyring and remove the key from the file.

---

### 4.1 — `pd.ExcelFile` not closed — file-handle leak

**Severity:** High
**File:** `convert_data.py` lines 152, 160

```python
def _read_xls(path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(path)              # line 152 — never closed
    sheet = ...
    return pd.read_excel(path, ...)

def _read_ods(path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(path, engine="odf")  # line 160 — never closed
    sheet = ...
    raw = xl.parse(...)
    return xl.parse(...)
```

If `_header_skiprows`, `_find_header_row`, or `xl.parse` raises, `xl` is never
closed. On Windows this causes file-locking for the lifetime of the process (or
until GC), preventing the user from moving/deleting the source file.

`_read_xls` (line 152) creates an `ExcelFile` but then uses `pd.read_excel`
directly — the `ExcelFile` is unused after `xl.sheet_names`. In `_read_ods`
the object is genuinely used.

**Fix for `_read_xls`:** remove the unnecessary `ExcelFile` and detect the
sheet name via `pd.ExcelFile` as a context manager, or use
`pd.ExcelFile.__enter__`/`__exit__`:

```python
def _read_xls(path: Path) -> pd.DataFrame:
    with pd.ExcelFile(path) as xl:
        sheet = "MasterData" if "MasterData" in xl.sheet_names else xl.sheet_names[0]
    skip = _header_skiprows(path, sheet)
    return pd.read_excel(path, sheet_name=sheet, skiprows=skip)
```

**Fix for `_read_ods`:**
```python
def _read_ods(path: Path) -> pd.DataFrame:
    with pd.ExcelFile(path, engine="odf") as xl:
        sheet = "MasterData" if "MasterData" in xl.sheet_names else xl.sheet_names[0]
        raw = xl.parse(sheet, header=None, nrows=10)
        skip = _find_header_row(raw)
        return xl.parse(sheet, skiprows=skip)
```

---

### 5.1 — Duplicate DataFrame row-lookup in email send loop

**Severity:** Medium
**File:** `app/gui_email_send.py` lines 461–479

The same `df_snap` filter is executed twice in sequence to extract `email_address`
and `reportsent` from the same row:

```python
# lookup 1
if df_snap is not None:
    matches = df_snap[(df_snap["company_name"].str.strip() == company.strip()) & ...]
    if not matches.empty:
        email = matches.iloc[0].get("email_address", "")

# lookup 2
if df_snap is not None and "reportsent" in df_snap.columns:
    matches = df_snap[(df_snap["company_name"].str.strip() == company.strip()) & ...]
    if not matches.empty:
        is_sent = matches.iloc[0].get("reportsent", False)
```

Doubles the filter cost per file and violates DRY.

**Fix:** Extract a `_find_row(df, company, person)` helper that returns the
matched `Series | None`, then read both columns from it once.

---

### 5.2 — `_cell_text()` returns `None` for empty cells

**Severity:** Low
**File:** `convert_data.py` lines 128–130

```python
def _cell_text(cell: ET.Element) -> str | None:
    data = cell.find(f"{ns}Data")
    return data.text if data is not None else None
```

`data.text` is also `None` when the element exists but has no content. Callers
build dicts that then contain `None` values for empty cells, which propagate as
`None` into the CSV instead of empty strings, and require `pd.isna()` checks
downstream.

**Fix:** Return `""` as default:
```python
def _cell_text(cell: ET.Element) -> str:
    data = cell.find(f"{ns}Data")
    return data.text or "" if data is not None else ""
```

---

### 5.3 — Hardcoded `"[TEST MODE]"` literal

**Severity:** Low
**File:** `app/gui_email_send.py` ~line 824

`" [TEST MODE]"` appears as a string literal. It should be a constant in
`utils/constants.py` alongside `SMTP_TIMEOUT_SECONDS` etc.

**Fix:**
```python
# utils/constants.py
TEST_MODE_LABEL = "[TEST MODE]"

# gui_email_send.py
from utils.constants import ..., TEST_MODE_LABEL
test_mode_str = f" {TEST_MODE_LABEL}" if test_mode else ""
```

---

## Proposed milestones

| Milestone | Findings | Summary |
|-----------|----------|---------|
| M52 | 1.1, 1.2, 1.3, 2.1, 4.1 | Thread safety + resource leaks |
| M53 | 3.1 | Security: keyring credential storage |
| M54 | 5.1, 5.2, 5.3 | Code quality quick wins |

#!/bin/bash
# setup_macos.sh -- installs R, Quarto, TinyTeX and required R packages on macOS.
# Can be run manually after installing the app:
#   bash ~/Applications/ResilenceScanReportBuilder/setup_macos.sh
# Or run automatically by the app on first launch.

set -e

QUARTO_VERSION="1.6.39"
FLAG_DIR="$HOME/Library/Application Support/ResilienceScan"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
R_LIB="$INSTALL_DIR/r-library"

log() { echo "[SETUP] $1"; }

# Default to FAIL; overwritten to PASS only when all steps complete cleanly.
SETUP_RESULT="FAIL"

mkdir -p "$FLAG_DIR"

# Write running flag immediately so the app knows setup is in progress.
echo "running" > "$FLAG_DIR/setup_running.flag"

# On any exit (normal or error) write the completion flag.
_on_exit() {
    echo "$SETUP_RESULT" > "$FLAG_DIR/setup_complete.flag"
    rm -f "$FLAG_DIR/setup_running.flag"
    if [ "$SETUP_RESULT" = "PASS" ]; then
        osascript -e 'display notification "Setup complete. You can now generate reports." with title "ResilienceScan"' 2>/dev/null || true
    else
        osascript -e 'display notification "Setup finished with errors. Check ~/Library/Logs/ResilienceScan/setup.log" with title "ResilienceScan" subtitle "Error"' 2>/dev/null || true
    fi
}
trap _on_exit EXIT

# Redirect all output to a log file as well
mkdir -p "$HOME/Library/Logs/ResilienceScan"
exec > >(tee -a "$HOME/Library/Logs/ResilienceScan/setup.log") 2>&1

log "ResilienceScan macOS dependency setup starting..."

# -- Homebrew -----------------------------------------------------------------
if ! command -v brew &>/dev/null; then
    log "Homebrew not found. Please install Homebrew first: https://brew.sh"
    log "Then re-run this script."
    exit 1
fi

# -- R ------------------------------------------------------------------------
R_MIN_MAJOR=4
R_MIN_MINOR=4

_r_version_ok() {
    local ver major minor
    ver=$(Rscript --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "0.0.0")
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    [ "$major" -gt "$R_MIN_MAJOR" ] || \
        ([ "$major" -eq "$R_MIN_MAJOR" ] && [ "$minor" -ge "$R_MIN_MINOR" ])
}

R_UPGRADED=false
if ! command -v Rscript &>/dev/null; then
    log "R not found - installing via Homebrew..."
    brew install --cask r
    R_UPGRADED=true
elif ! _r_version_ok; then
    INSTALLED_R=$(Rscript --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
    log "R $INSTALLED_R found but older than required ${R_MIN_MAJOR}.${R_MIN_MINOR} - upgrading..."
    brew upgrade --cask r || brew install --cask r
    R_UPGRADED=true
else
    INSTALLED_R=$(Rscript --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
    log "R $INSTALLED_R already meets requirements (>= ${R_MIN_MAJOR}.${R_MIN_MINOR}) - skipping install."
fi

# -- Quarto -------------------------------------------------------------------
if ! command -v quarto &>/dev/null; then
    log "Downloading Quarto $QUARTO_VERSION for macOS..."
    TMP=$(mktemp -d)
    # Try arm64 first (Apple Silicon), fall back to x86_64 (Intel)
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        PKG_URL="https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-macos.pkg"
    else
        PKG_URL="https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-macos.pkg"
    fi
    curl -L -o "$TMP/quarto.pkg" "$PKG_URL"
    sudo installer -pkg "$TMP/quarto.pkg" -target /
    rm -rf "$TMP"
else
    log "Quarto already present -- skipping."
fi

# -- TinyTeX ------------------------------------------------------------------
if ! command -v tlmgr &>/dev/null && \
   ! [ -f "$HOME/Library/Application Support/quarto/tools/tinytex/bin/universal-darwin/tlmgr" ]; then
    log "Installing TinyTeX via Quarto..."
    quarto install tinytex --no-prompt
else
    log "TinyTeX already present -- skipping."
fi

# -- R packages ---------------------------------------------------------------
log "Installing R packages into $R_LIB..."

# If R was upgraded, wipe the old r-library to avoid binary compatibility issues.
if [ "$R_UPGRADED" = "true" ] && [ -d "$R_LIB" ]; then
    log "R was upgraded - removing stale r-library: $R_LIB"
    rm -rf "$R_LIB"
fi

mkdir -p "$R_LIB"

NCPUS=$(sysctl -n hw.logicalcpu 2>/dev/null || echo 2)
R_PKGS="'readr','dplyr','stringr','tidyr','ggplot2','knitr','fmsb','scales','viridis','patchwork','RColorBrewer','gridExtra','png','lubridate','kableExtra','rmarkdown','jsonlite','ggrepel','cowplot'"

Rscript -e "
  pkgs <- c($R_PKGS)
  install.packages(pkgs, lib='$R_LIB', repos='https://cloud.r-project.org', Ncpus=${NCPUS}, quiet=FALSE)
"

# Verify all packages installed and loadable
log "Verifying R packages..."

if ! command -v Rscript &>/dev/null; then
    log "ERROR: Rscript not found on PATH - cannot verify R packages."
    SETUP_RESULT="FAIL"
else
    MISSING=$(Rscript --no-save -e "
  .libPaths(c('$R_LIB', .libPaths()))
  pkgs <- c($R_PKGS)
  bad <- pkgs[!sapply(pkgs, requireNamespace, quietly=TRUE)]
  cat(paste(bad, collapse=' '))
" 2>&1) || { log "WARNING: Rscript package check failed"; MISSING="check_failed"; }

    if [ -n "$MISSING" ]; then
        log "Retrying packages that failed to load: $MISSING"
        for pkg in $MISSING; do
            Rscript -e "install.packages('$pkg', lib='$R_LIB', repos='https://cloud.r-project.org')" 2>&1 || true
        done
        STILL_MISSING=$(Rscript --no-save -e "
      .libPaths(c('$R_LIB', .libPaths()))
      pkgs <- c($R_PKGS)
      bad <- pkgs[!sapply(pkgs, requireNamespace, quietly=TRUE)]
      cat(paste(bad, collapse=' '))
" 2>&1) || { log "WARNING: Rscript final check failed"; STILL_MISSING="check_failed"; }
        if [ -n "$STILL_MISSING" ]; then
            log "ERROR: R packages still not loadable after retry: $STILL_MISSING"
            SETUP_RESULT="FAIL"
        else
            log "R package retry succeeded -- all packages installed and loadable."
            SETUP_RESULT="PASS"
        fi
    else
        log "R package verification: all packages installed and loadable."
        SETUP_RESULT="PASS"
    fi
fi

log "Dependency setup complete. Result: $SETUP_RESULT"

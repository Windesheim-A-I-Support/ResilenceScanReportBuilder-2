<#
.SYNOPSIS
    Silently installs R, Quarto, TinyTeX and required R/LaTeX packages.
    Runs as SYSTEM via Task Scheduler -- no UAC prompts, no execution-policy blocks.
    Progress is logged to C:\ProgramData\ResilienceScan\setup.log
    Full transcript (all output + errors) at C:\ProgramData\ResilienceScan\setup_transcript.log

.PARAMETER InstallDir
    Installation directory (default: directory containing this script).
#>
param(
    [string]$InstallDir = $PSScriptRoot
)

# PS 5.1 compatible -- do NOT use ?. null-conditional operator (PS 7+ only).
$ProgressPreference    = "SilentlyContinue"   # suppress slow progress bars
$ErrorActionPreference = "Continue"           # don't silently swallow errors

$LOG_DIR    = "C:\ProgramData\ResilienceScan"
$LOG_FILE   = "$LOG_DIR\setup.log"
$TRANSCRIPT = "$LOG_DIR\setup_transcript.log"
$ERROR_LOG  = "$LOG_DIR\setup_error.log"

# Ensure log directory exists before anything else
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

# Signal that setup is in progress so the app can show a helpful message
"running" | Set-Content "$LOG_DIR\setup_running.flag" -Encoding UTF8

# Capture EVERYTHING (stdout + stderr + errors) to the transcript
Start-Transcript -Path $TRANSCRIPT -Append -Force | Out-Null

# Global trap: any terminating error writes to setup_error.log + setup.log
trap {
    $errMsg  = $_.Exception.Message
    $errStk  = $_.ScriptStackTrace
    $fatLine = "[FATAL $(Get-Date -Format 'HH:mm:ss')] Unhandled error: $errMsg"
    Write-Host $fatLine
    Add-Content -Path $ERROR_LOG -Value $fatLine           -Encoding UTF8
    Add-Content -Path $ERROR_LOG -Value $errStk            -Encoding UTF8
    Add-Content -Path $LOG_FILE  -Value $fatLine           -Encoding UTF8
    Add-Content -Path $LOG_FILE  -Value $errStk            -Encoding UTF8
    Stop-Transcript | Out-Null
    exit 1
}

$R_VERSION      = "4.5.1"
$QUARTO_VERSION = "1.6.39"

# ---- Logging ----------------------------------------------------------------
function Write-Log {
    param($msg)
    $line = "[SETUP $(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}
$R_LIB          = "$InstallDir\r-library"
$TMP            = "C:\Windows\Temp"        # reliable under SYSTEM account

$R_PACKAGES = @(
    "readr", "dplyr", "stringr", "tidyr", "ggplot2", "knitr",
    "fmsb", "scales", "viridis", "patchwork", "RColorBrewer",
    "gridExtra", "png", "lubridate", "kableExtra", "rmarkdown",
    "jsonlite", "ggrepel", "cowplot"
)

# LaTeX packages required by ResilienceReport.qmd + kableExtra dependencies.
# Use TLmgr repository package names (not LaTeX command/file names):
#   afterpage  -> preprint  (preprint bundle contains afterpage.sty)
#   graphicx   -> graphics  (graphics bundle contains graphicx.sty)
#   array      -> omitted   (part of LaTeX base / tools, already in TinyTeX core)
#   longtable  -> omitted   (part of tools bundle, already listed)
#   tikz       -> omitted   (provided by pgf, already listed)
$LATEX_PACKAGES = @(
    "pgf", "xcolor", "colortbl", "booktabs", "multirow",
    "float", "wrapfig", "pdflscape", "geometry", "preprint", "graphics",
    "tabu", "threeparttable", "threeparttablex", "ulem", "makecell",
    "environ", "trimspaces", "caption", "hyperref",
    "setspace", "fancyhdr", "microtype", "lm", "needspace", "varwidth",
    "mdwtools", "xstring", "tools"
)

Write-Log "=== ResilienceScan dependency setup started (running as SYSTEM) ==="
Write-Log "InstallDir : $InstallDir"
Write-Log "R_LIB      : $R_LIB"
Write-Log "Transcript : $TRANSCRIPT"
Write-Log "PS version : $($PSVersionTable.PSVersion)"
Write-Log "Running as : $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

# ---- Helper: find Rscript.exe (PS 5.1 compatible -- no ?. operator) ---------
function Find-Rscript {
    # Prefer the target R version explicitly - this ensures that after a
    # version upgrade the new R binary is used even when the old version is
    # still first on PATH.
    $candidates = @(
        "C:\Program Files\R\R-$R_VERSION\bin\Rscript.exe",
        "C:\Program Files\R\R-$R_VERSION\bin\x64\Rscript.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    # Fall back to whatever PATH resolves to
    $cmd = Get-Command Rscript -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Last resort: scan for any R installation, newest version first
    # (Sort-Object on the full path gives ascending version order, so
    #  -Descending returns the highest R-x.y.z directory first.)
    $found = Get-ChildItem "C:\Program Files\R" -Filter "Rscript.exe" `
                 -Recurse -ErrorAction SilentlyContinue |
             Sort-Object FullName -Descending |
             Select-Object -First 1 -ExpandProperty FullName
    return $found
}

function Refresh-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
}

# ---- R ----------------------------------------------------------------------
# Install the discovered version if (a) no R is found, or (b) the installed
# version is older than the required version (ensures binary packages exist).
function Get-InstalledRVersion($rscript) {
    if (-not $rscript) { return $null }
    try {
        $out = (& $rscript --version 2>&1) -join " "
        if ($out -match "R version (\d+\.\d+\.\d+)") { return [version]$matches[1] }
    } catch {}
    return $null
}

$rscriptBefore    = Find-Rscript
$installedVersion = Get-InstalledRVersion $rscriptBefore
$requiredVersion  = [version]$R_VERSION

$needInstall = $false
if (-not $rscriptBefore) {
    Write-Log "R not found - installing $R_VERSION..."
    $needInstall = $true
} elseif ($installedVersion -and ($installedVersion -lt $requiredVersion)) {
    Write-Log "R $installedVersion found but < $R_VERSION - upgrading to latest..."
    $needInstall = $true
} else {
    Write-Log "R $installedVersion already present and up to date - skipping install."
}

if ($needInstall) {
    # Try current-release URL first; if not found, fall back to /old/ archive.
    $rTmp = "$TMP\R-$R_VERSION-win.exe"
    $rUrls = @(
        "https://cran.r-project.org/bin/windows/base/R-$R_VERSION-win.exe",
        "https://cran.r-project.org/bin/windows/base/old/$R_VERSION/R-$R_VERSION-win.exe"
    )
    $downloaded = $false
    foreach ($rUrl in $rUrls) {
        try {
            Write-Log "  Trying: $rUrl"
            Invoke-WebRequest -Uri $rUrl -OutFile $rTmp -UseBasicParsing
            $sizeMB = [math]::Round((Get-Item $rTmp).Length / 1MB, 1)
            Write-Log "  Download complete ($sizeMB MB)"
            $downloaded = $true
            break
        } catch {
            Write-Log "  URL failed: $($_.Exception.Message)"
        }
    }
    if ($downloaded) {
        try {
            Write-Log "Installing R $R_VERSION (silent, all users)..."
            $proc = Start-Process -FilePath $rTmp `
                        -ArgumentList "/VERYSILENT", "/NORESTART", "/ALLUSERS" `
                        -Wait -PassThru
            Write-Log "  R installer exit code: $($proc.ExitCode)"
            Remove-Item $rTmp -Force -ErrorAction SilentlyContinue
            Refresh-Path
            $rAfter = Find-Rscript
            if ($rAfter) {
                Write-Log "R installed successfully: $rAfter"
            } else {
                Write-Log "WARNING: R installer finished but Rscript.exe not found."
            }
        } catch {
            $errMsg = $_.Exception.Message
            $errStk = $_.ScriptStackTrace
            Write-Log "ERROR installing R: $errMsg"
            Write-Log "  Stack: $errStk"
            Add-Content -Path $ERROR_LOG -Value "[R install] $errMsg" -Encoding UTF8
            Add-Content -Path $ERROR_LOG -Value $errStk               -Encoding UTF8
        }
    } else {
        Write-Log "ERROR: Could not download R $R_VERSION from any URL."
        Add-Content -Path $ERROR_LOG -Value "[R install] Failed to download R $R_VERSION" -Encoding UTF8
    }
}

# ---- Quarto -----------------------------------------------------------------
$quartoCmd  = Get-Command quarto -ErrorAction SilentlyContinue
$quartoPath = if ($quartoCmd) { $quartoCmd.Source } else { $null }
if (-not $quartoPath) {
    Write-Log "Downloading Quarto $QUARTO_VERSION..."
    $qUrl = "https://github.com/quarto-dev/quarto-cli/releases/download/v$QUARTO_VERSION/quarto-$QUARTO_VERSION-win.msi"
    $qTmp = "$TMP\quarto-$QUARTO_VERSION.msi"
    try {
        Write-Log "  URL: $qUrl"
        Invoke-WebRequest -Uri $qUrl -OutFile $qTmp -UseBasicParsing
        $sizeMB = [math]::Round((Get-Item $qTmp).Length / 1MB, 1)
        Write-Log "  Download complete ($sizeMB MB)"
        Write-Log "Installing Quarto $QUARTO_VERSION (silent)..."
        $proc = Start-Process -FilePath msiexec `
                    -ArgumentList "/i", $qTmp, "/qn", "/norestart" `
                    -Wait -PassThru
        Write-Log "  msiexec exit code: $($proc.ExitCode)"
        Remove-Item $qTmp -Force -ErrorAction SilentlyContinue
        Refresh-Path
        $quartoAfter = Get-Command quarto -ErrorAction SilentlyContinue
        if ($quartoAfter) {
            Write-Log "Quarto installed successfully: $($quartoAfter.Source)"
        } else {
            Write-Log "WARNING: Quarto installer finished but quarto not found on PATH."
        }
    } catch {
        $errMsg = $_.Exception.Message
        $errStk = $_.ScriptStackTrace
        Write-Log "ERROR installing Quarto: $errMsg"
        Write-Log "  Stack: $errStk"
        Add-Content -Path $ERROR_LOG -Value "[Quarto install] $errMsg" -Encoding UTF8
        Add-Content -Path $ERROR_LOG -Value $errStk                    -Encoding UTF8
    }
} else {
    Write-Log "Quarto already present: $quartoPath - skipping."
}

# ---- TinyTeX ----------------------------------------------------------------
# quarto install tinytex installs to the current user's (SYSTEM's) APPDATA.
# Quarto 1.4+ uses %APPDATA%\quarto\tools\tinytex\; older versions used
# %APPDATA%\TinyTeX\ directly.  After install we locate the bin dir, grant
# other users read+execute access, and add it to machine-wide PATH so regular
# users can find tlmgr/lualatex.
$tlmgr = Get-Command tlmgr -ErrorAction SilentlyContinue
if (-not $tlmgr) {
    Write-Log "Installing TinyTeX via Quarto..."
    try {
        & quarto install tinytex --no-prompt 2>&1 | ForEach-Object { Write-Log "  [quarto] $_" }

        # Find where quarto put TinyTeX (varies by account and quarto version).
        # Quarto 1.4+ installs to quarto\tools\tinytex\; older versions to TinyTeX\.
        $tinyTexBin = $null
        $candidates = @(
            # Quarto 1.4+ tools dir (current account - SYSTEM when this script runs)
            "$env:APPDATA\quarto\tools\tinytex\bin\windows",
            "$env:LOCALAPPDATA\quarto\tools\tinytex\bin\windows",
            # Hardcoded SYSTEM profile quarto tools (in case env vars not set)
            "C:\Windows\system32\config\systemprofile\AppData\Roaming\quarto\tools\tinytex\bin\windows",
            "C:\Windows\system32\config\systemprofile\AppData\Local\quarto\tools\tinytex\bin\windows",
            # Legacy standalone TinyTeX location (older quarto / direct install)
            "$env:LOCALAPPDATA\TinyTeX\bin\windows",
            "$env:APPDATA\TinyTeX\bin\windows",
            "C:\Windows\system32\config\systemprofile\AppData\Local\TinyTeX\bin\windows",
            "C:\Windows\system32\config\systemprofile\AppData\Roaming\TinyTeX\bin\windows"
        )
        Write-Log "Searching for TinyTeX bin directory..."
        foreach ($c in $candidates) {
            $exists = if (Test-Path $c) { "FOUND" } else { "not found" }
            Write-Log "  Checking: $c -- $exists"
            if (Test-Path $c) { $tinyTexBin = $c; break }
        }

        if ($tinyTexBin) {
            Write-Log "TinyTeX found at: $tinyTexBin"
            $tinyTexRoot = Split-Path (Split-Path $tinyTexBin -Parent) -Parent

            # Copy TinyTeX to C:\ProgramData\TinyTeX so regular users can access
            # it without traversal restrictions from the SYSTEM account's AppData.
            # ProgramData is world-readable by default; this avoids ACL issues.
            $publicRoot = "C:\ProgramData\TinyTeX"
            $publicBin  = "$publicRoot\bin\windows"
            if (-not (Test-Path $publicRoot)) {
                Write-Log "Copying TinyTeX to $publicRoot (accessible to all users)..."
                try {
                    & robocopy $tinyTexRoot $publicRoot /E /NFL /NDL /NJH /NJS /NC /NS /NP /MT:4 2>&1 | Out-Null
                    Write-Log "TinyTeX copied to $publicRoot"
                } catch {
                    Write-Log "WARNING: robocopy failed ($($_.Exception.Message)) - falling back to original path."
                    $publicBin = $tinyTexBin   # fall back to original
                }
            } else {
                Write-Log "C:\ProgramData\TinyTeX already present - skipping copy."
            }

            # Add the public TinyTeX bin to machine-wide PATH
            $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
            if ($machinePath -notlike "*$publicBin*") {
                [System.Environment]::SetEnvironmentVariable(
                    "PATH", "$machinePath;$publicBin", "Machine")
                Write-Log "TinyTeX added to system PATH: $publicBin"
            } else {
                Write-Log "TinyTeX already in system PATH."
            }
            $env:PATH = "$env:PATH;$publicBin"
        } else {
            Write-Log "WARNING: TinyTeX bin dir not found after install - tlmgr will be unavailable."
        }
    } catch {
        $errMsg = $_.Exception.Message
        $errStk = $_.ScriptStackTrace
        Write-Log "ERROR installing TinyTeX: $errMsg"
        Write-Log "  Stack: $errStk"
        Add-Content -Path $ERROR_LOG -Value "[TinyTeX install] $errMsg" -Encoding UTF8
        Add-Content -Path $ERROR_LOG -Value $errStk                     -Encoding UTF8
    }
} else {
    Write-Log "TinyTeX already present: $($tlmgr.Source) - skipping install."
}

# Ensure TinyTeX is accessible to regular users via C:\ProgramData\TinyTeX.
# This copy is needed on reinstalls where tlmgr was already present (setup
# skipped the install block above) but the public copy was never created.
$publicRoot = "C:\ProgramData\TinyTeX"
if (-not (Test-Path $publicRoot)) {
    $tlmgrNow = Get-Command tlmgr -ErrorAction SilentlyContinue
    if ($tlmgrNow) {
        $tinyTexBinNow  = Split-Path $tlmgrNow.Source -Parent
        $tinyTexRootNow = Split-Path (Split-Path $tinyTexBinNow -Parent) -Parent
        Write-Log "Copying TinyTeX to $publicRoot for user accessibility (post-install)..."
        try {
            & robocopy $tinyTexRootNow $publicRoot /E /NFL /NDL /NJH /NJS /NC /NS /NP /MT:4 2>&1 | Out-Null
            Write-Log "TinyTeX copied to $publicRoot"
        } catch {
            Write-Log "WARNING: robocopy to ProgramData failed: $($_.Exception.Message)"
        }
        $publicBin = "$publicRoot\bin\windows"
        if (Test-Path $publicBin) {
            $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
            if ($machinePath -notlike "*$publicBin*") {
                [System.Environment]::SetEnvironmentVariable(
                    "PATH", "$machinePath;$publicBin", "Machine")
                Write-Log "TinyTeX (public) added to system PATH: $publicBin"
            }
            $env:PATH = "$env:PATH;$publicBin"
        }
    }
}

# ---- LaTeX packages ---------------------------------------------------------
$tlmgr = Get-Command tlmgr -ErrorAction SilentlyContinue
if ($tlmgr) {
    Write-Log "Installing LaTeX packages via tlmgr: $($tlmgr.Source)"

    # Pre-create directories that tlmgr's tar extractor may fail to create when
    # the texmf-dist tree is sparse (common in fresh TinyTeX installs).
    $tlmgrSrc    = $tlmgr.Source   # e.g. ...TinyTeX\bin\windows\tlmgr.bat
    $tinyTexRoot = Split-Path (Split-Path (Split-Path $tlmgrSrc))
    $preCreateDirs = @("tex\latex\capt-of", "tex\latex\preprint")
    foreach ($d in $preCreateDirs) {
        $fullPath = Join-Path $tinyTexRoot "texmf-dist\$d"
        if (-not (Test-Path $fullPath)) {
            New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
            Write-Log "Pre-created dir: $fullPath"
        }
    }

    try {
        & tlmgr install @LATEX_PACKAGES 2>&1 | ForEach-Object { Write-Log "  [tlmgr] $_" }
        Write-Log "LaTeX packages installed."
    } catch {
        $errMsg = $_.Exception.Message
        $errStk = $_.ScriptStackTrace
        Write-Log "ERROR installing LaTeX packages: $errMsg"
        Write-Log "  Stack: $errStk"
        Add-Content -Path $ERROR_LOG -Value "[LaTeX packages] $errMsg" -Encoding UTF8
        Add-Content -Path $ERROR_LOG -Value $errStk                    -Encoding UTF8
    }

    # capt-of: tlmgr's bundled tar.exe fails to extract capt-of.tar on fresh
    # TinyTeX because the target directory does not exist and tar cannot create it.
    # Workaround: write a minimal capt-of.sty stub directly, then refresh the
    # filename database with mktexlsr so LaTeX can find it.
    $captOfDir  = Join-Path $tinyTexRoot "texmf-dist\tex\latex\capt-of"
    $captOfFile = Join-Path $captOfDir "capt-of.sty"
    if (-not (Test-Path $captOfFile)) {
        New-Item -ItemType Directory -Force -Path $captOfDir | Out-Null
        $captOfStub = @'
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{capt-of}[2011/08/12 v0.2 non-floating captions (stub)]
\newcommand\captionof[2][\@captype]{\def\@captype{#1}\caption{#2}}
'@
        Set-Content -Path $captOfFile -Value $captOfStub -Encoding UTF8
        Write-Log "Written capt-of.sty stub to: $captOfFile"
        & mktexlsr 2>&1 | ForEach-Object { Write-Log "  [mktexlsr] $_" }
        Write-Log "mktexlsr complete."
    } else {
        Write-Log "capt-of.sty already present - skipping stub."
    }
} else {
    Write-Log "WARNING: tlmgr not found - LaTeX packages skipped."
}

# ---- R packages -------------------------------------------------------------
$rscript = Find-Rscript
if ($rscript) {
    Write-Log "Installing R packages into $R_LIB (using $rscript)..."
    New-Item -ItemType Directory -Force -Path $R_LIB | Out-Null
    # Grant Users read access to the R library so the app can load packages
    icacls $R_LIB /grant "BUILTIN\Users:(OI)(CI)RX" /T /Q 2>&1 | Out-Null
    $pkgList = ($R_PACKAGES | ForEach-Object { "'" + $_ + "'" }) -join ", "
    # R requires forward slashes in paths - backslashes in Windows paths cause
    # "unrecognized escape" errors (e.g. \P in \Program Files is not a valid escape).
    $R_LIB_R = $R_LIB.Replace('\', '/')
    try {
        # type='binary' forces pre-compiled Windows packages - avoids source-build
        # failures where a package (e.g. ggrepel) is listed as "not available" when
        # only the source version exists for that R minor version.
        & $rscript -e "install.packages(c($pkgList), lib='$R_LIB_R', repos='https://cloud.r-project.org', type='binary', quiet=FALSE)" 2>&1 |
            ForEach-Object { Write-Log "  [R] $_" }

        # Verify all packages actually installed - type='binary' + quiet=FALSE still
        # doesn't set a non-zero exit code on partial failure, so check explicitly.
        $verifyScript = "missing <- c($pkgList)[!c($pkgList) %in% rownames(installed.packages(lib.loc='$R_LIB_R'))]; if(length(missing)==0) cat('OK') else cat('MISSING:', paste(missing, collapse=','))"
        $verifyOut = (& $rscript --no-save -e $verifyScript 2>&1) -join " "
        if ($verifyOut -match "^OK") {
            Write-Log "R package verification: all $($R_PACKAGES.Count) packages present."
        } else {
            Write-Log "WARNING: Some packages missing after bulk install - retrying individually: $verifyOut"
            Add-Content -Path $ERROR_LOG -Value "[R packages verify] $verifyOut" -Encoding UTF8
            # Retry each missing package one at a time with binary type
            $missingCsv = ($verifyOut -replace "MISSING:\s*", "").Trim()
            foreach ($pkg in ($missingCsv -split ",\s*")) {
                $pkg = $pkg.Trim()
                if ($pkg) {
                    Write-Log "  Retrying: $pkg"
                    & $rscript -e "install.packages('$pkg', lib='$R_LIB_R', repos='https://cloud.r-project.org', type='binary')" 2>&1 |
                        ForEach-Object { Write-Log "  [R retry] $_" }
                }
            }
            # Final check after retry
            $finalOut = (& $rscript --no-save -e $verifyScript 2>&1) -join " "
            if ($finalOut -match "^OK") {
                Write-Log "R package verification after retry: all $($R_PACKAGES.Count) packages present."
            } else {
                Write-Log "ERROR: R packages still missing after retry: $finalOut"
                Add-Content -Path $ERROR_LOG -Value "[R packages retry] $finalOut" -Encoding UTF8
            }
        }
    } catch {
        $errMsg = $_.Exception.Message
        $errStk = $_.ScriptStackTrace
        Write-Log "ERROR installing R packages: $errMsg"
        Write-Log "  Stack: $errStk"
        Add-Content -Path $ERROR_LOG -Value "[R packages] $errMsg" -Encoding UTF8
        Add-Content -Path $ERROR_LOG -Value $errStk                -Encoding UTF8
    }
} else {
    Write-Log "WARNING: Rscript not found - R packages not installed."
}

Write-Log "=== Dependency setup complete ==="

# ---- Requirements verification report ---------------------------------------
# Written to requirements_check.log so users and the app can read a clear
# PASS/FAIL summary without parsing the full setup transcript.
$REQ_LOG = "$LOG_DIR\requirements_check.log"
$stamp    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$lines    = @()
$allOk    = $true

function Req-Line($label, $ok, $detail) {
    $status = if ($ok) { "OK  " } else { "FAIL" }
    return "  [$status] $label : $detail"
}

$lines += "ResilienceScan requirements check - $stamp"
$lines += "=" * 60

# -- R ------------------------------------------------------------------------
$rscript = Find-Rscript
if ($rscript) {
    $rVer = (& $rscript --version 2>&1) -join " "
    if ($rVer -match "R version (\S+)") { $rVer = "R $($matches[1])" }
    $lines += Req-Line "R         " $true  "$rVer  ($rscript)"
    # Add R bin dir to PATH so subsequent checks can use Rscript by name
    $rBin = Split-Path $rscript
    $env:PATH = "$rBin;$env:PATH"
} else {
    $lines += Req-Line "R         " $false "NOT FOUND - install from https://cran.r-project.org"
    $allOk = $false
}

# -- Quarto -------------------------------------------------------------------
$quartoCmd = Get-Command quarto -ErrorAction SilentlyContinue
if ($quartoCmd) {
    $qVer = (& quarto --version 2>&1) -join ""
    $lines += Req-Line "Quarto    " $true  "Quarto $($qVer.Trim())  ($($quartoCmd.Source))"
} else {
    $lines += Req-Line "Quarto    " $false "NOT FOUND - install from https://quarto.org"
    $allOk = $false
}

# -- TinyTeX (tlmgr) ----------------------------------------------------------
$tlmgrCandidates = @(
    "C:\ProgramData\TinyTeX\bin\windows\tlmgr.bat",
    "$env:APPDATA\quarto\tools\tinytex\bin\windows\tlmgr.bat",
    "$env:LOCALAPPDATA\quarto\tools\tinytex\bin\windows\tlmgr.bat",
    "C:\Windows\system32\config\systemprofile\AppData\Roaming\TinyTeX\bin\windows\tlmgr.bat",
    "C:\Windows\system32\config\systemprofile\AppData\Local\TinyTeX\bin\windows\tlmgr.bat",
    "C:\Windows\system32\config\systemprofile\AppData\Roaming\quarto\tools\tinytex\bin\windows\tlmgr.bat",
    "C:\Windows\system32\config\systemprofile\AppData\Local\quarto\tools\tinytex\bin\windows\tlmgr.bat"
)
$tlmgrPath = ($tlmgrCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
if (-not $tlmgrPath) {
    $cmd = Get-Command tlmgr -ErrorAction SilentlyContinue
    if ($cmd) { $tlmgrPath = $cmd.Source }
}
if ($tlmgrPath) {
    $tlVer = (cmd /c "$tlmgrPath" --version 2>&1) -join " "
    if ($tlVer -match "TeX Live (\d+)") { $tlVer = "TinyTeX / TeX Live $($matches[1])" }
    $lines += Req-Line "TinyTeX   " $true  "$tlVer  ($tlmgrPath)"
} else {
    $lines += Req-Line "TinyTeX   " $false "tlmgr NOT FOUND - run: quarto install tinytex"
    $allOk = $false
}

# -- R packages ---------------------------------------------------------------
$lines += ""
$lines += "  R packages (lib: $R_LIB):"
if ($rscript -and (Test-Path $R_LIB)) {
    $pkgList  = ($R_PACKAGES | ForEach-Object { "'$_'" }) -join ", "
    $R_LIB_R  = $R_LIB.Replace('\', '/')
    $checkScript = "pkgs <- c($pkgList); inst <- rownames(installed.packages(lib.loc='$R_LIB_R')); for(p in pkgs){ cat(if(p %in% inst) 'OK' else 'MISSING', p, '\n') }"
    $pkgResults  = (& $rscript --no-save -e $checkScript 2>&1)
    $missingPkgs = @()
    foreach ($line in $pkgResults) {
        if ($line -match "^(OK|MISSING)\s+(\S+)") {
            $pkgOk   = ($matches[1] -eq "OK")
            $pkgName = $matches[2]
            $lines  += "    $(if($pkgOk){'[OK  ]'}else{'[FAIL]'}) $pkgName"
            if (-not $pkgOk) { $missingPkgs += $pkgName; $allOk = $false }
        }
    }
    if ($missingPkgs.Count -eq 0) {
        $lines += "  [OK  ] All $($R_PACKAGES.Count) required packages present"
    } else {
        $lines += "  [FAIL] Missing packages ($($missingPkgs.Count)): $($missingPkgs -join ', ')"
    }
} elseif (-not $rscript) {
    $lines += "    [SKIP] Cannot check - R not found"
} else {
    $lines += "    [FAIL] r-library directory not found: $R_LIB"
    $allOk = $false
}

# -- Summary -------------------------------------------------------------------
$lines += ""
$lines += "=" * 60
if ($allOk) {
    $lines += "RESULT: PASS - all requirements met. App is ready to generate reports."
} else {
    $lines += "RESULT: FAIL - one or more requirements are missing."
    $lines += "        Re-run setup or check setup_error.log for details."
}
$lines += "=" * 60

# Write the report
$lines | Set-Content -Path $REQ_LOG -Encoding UTF8
# Also echo to the main log
$lines | ForEach-Object { Write-Log $_ }

Write-Log "Requirements check written to: $REQ_LOG"
Write-Log "Log files:"
Write-Log "  Main log   : $LOG_FILE"
Write-Log "  Req check  : $REQ_LOG"
Write-Log "  Transcript : $TRANSCRIPT"
Write-Log "  Error log  : $ERROR_LOG"

Stop-Transcript | Out-Null

# Write completion flag for the app to read on next launch / while polling
if ($allOk) {
    "PASS" | Set-Content "$LOG_DIR\setup_complete.flag" -Encoding UTF8
} else {
    "FAIL" | Set-Content "$LOG_DIR\setup_complete.flag" -Encoding UTF8
}
Remove-Item "$LOG_DIR\setup_running.flag" -ErrorAction SilentlyContinue

# Best-effort desktop notification for the logged-in user.
# msg.exe works on Windows Pro/Enterprise from SYSTEM; harmless if unavailable.
try {
    if ($allOk) {
        & cmd /c "msg * /time:300 `"ResilienceScan: setup complete. You can now generate reports.`"" 2>$null
    } else {
        & cmd /c "msg * /time:300 `"ResilienceScan: setup finished with errors. See C:\ProgramData\ResilienceScan\setup.log`"" 2>$null
    }
} catch { }

# Self-delete the scheduled task now that setup is done
Unregister-ScheduledTask -TaskName "ResilienceScanSetup" -Confirm:$false -ErrorAction SilentlyContinue

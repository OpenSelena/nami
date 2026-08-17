<div align="center">

# 🌊 Nami

### *An open-source CLI media downloader for Instagram, TikTok, Facebook, and X*

[![CI](https://img.shields.io/github/actions/workflow/status/OpenSelena/nami/ci.yml?branch=main&style=for-the-badge&logo=github&label=CI)](https://github.com/OpenSelena/nami/actions/workflows/ci.yml)
[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2e7d32.svg?style=for-the-badge)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/OpenSelena/nami?style=for-the-badge&color=D97757)](https://github.com/OpenSelena/nami)

<p align="center">
  <b>Nami</b> is a lightweight, open-source media downloader designed for seamless batch extraction across social platforms. Combining <b>gallery-dl</b> and <b>yt-dlp</b> with an interactive <b>Rich terminal interface</b> and scriptable CLI workflows, Nami automates deduplication, rate-limit retries, and browser cookie handling.
</p>

[Installation](#installation) • [Quickstart](#quickstart) • [Supported Platforms](#supported-platforms) • [CLI Commands](#cli-commands-reference) • [Configuration](#configuration--environment-variables) • [Diagnostics](#diagnostics) • [Troubleshooting](#troubleshooting)

</div>

---

## Features

- **Multi-Platform Batch Downloads**: Extract high-resolution photos, videos, reels, posts, stories, and highlights.
- **Dual-Engine Architecture**: Intelligently routes tasks between `gallery-dl` and `yt-dlp` with automatic fallback on extractor failures.
- **Interactive & Headless Modes**: Run interactively with an intuitive terminal UI or integrate into headless pipelines with dedicated CLI subcommands and `--json` output.
- **Smart Anti-Duplicate Archiving**: Maintains per-target `archive.txt` records to avoid redundant re-downloads, with safe `archive reset` management.
- **Flexible Authentication**: Supports Netscape cookie files, anonymous fallbacks, and direct browser cookie extraction (`--cookies-from-browser`).
- **Resilient Retry & Failure Classification**: Classifies auth, cookie, rate-limit, network, dependency, not-found, extractor, and timeout failures with exponential jittered backoff.
- **Built-in System Doctor**: Run `nami doctor` to verify local binaries, browser installations, cookie permissions, and workspace health without network calls.

---

## Supported Platforms

| Platform | Photos / Posts | Videos / Reels | Stories | Highlights | Auth Support | Primary Engine |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Instagram** | Included | Included | Included | Included | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |
| **TikTok** | Limited by upstream | Included | N/A | N/A | Browser DB / Netscape Cookie | `yt-dlp` / `gallery-dl` |
| **Facebook** | Limited by upstream | Included | N/A | N/A | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |
| **X (Twitter)** | Limited by upstream | Included | N/A | N/A | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |

> [!NOTE]
> Unsupported media combinations are reported as unsupported operations instead of silently failing or being treated as successful downloads.

---

## Installation

Install `nami` directly via `pip`:

```bash
python -m pip install nami
```

*Runtime dependencies (`rich`, `gallery-dl`, `yt-dlp`) are automatically installed.*

To upgrade to the latest release:

```bash
python -m pip install --upgrade nami
```

Nami requires **Python 3.10 or newer**.

---

## Quickstart

### 1. Interactive Mode
Run `nami` without arguments to launch the interactive terminal UI:

```bash
nami
```

```text
┌──────────────────────── Nami ────────────────────────┐
│ What do you want to download?                        │
│                                                      │
│  1  Photos only                                      │
│  2  Videos only                                      │
│  3  Stories only                                     │
│  4  Highlights only                                  │
│  5  Photos + Videos                                  │
│  6  Stories + Highlights                             │
│  7  All                                              │
│  8  Settings                                         │
│  0  Exit                                             │
│                                                      │
│  Save: ~/Nami/downloads                              │
└──────────────────────────────────────────────────────┘
```

On first launch, Nami guides you through workspace initialization. Workspace setup is explicit and never creates files as hidden import-time side effects.

### 2. Workspace Layout
Nami organizes downloads, cookie files, and target profile lists cleanly:

```text
Nami/
├── downloads/      # Extracted media organized by platform, account & kind
├── cookies/        # Optional Netscape cookie files (*_cookies.txt)
└── profiles/       # Target profile URLs (*_profiles.txt)
    ├── facebook_profiles.txt
    ├── instagram_profiles.txt
    ├── tiktok_profiles.txt
    └── x_profiles.txt
```

---

## CLI Commands Reference

Nami provides a full suite of scriptable subcommands for headless pipelines and automation:

### `nami setup`
Initialize a Nami workspace directory structure and configuration:

```bash
# Initialize workspace under current directory
nami setup --root .

# Initialize with template cookie files
nami setup --root /path/to/workspace --cookie-templates

# Output JSON report
nami setup --root . --json
```

### `nami download`
Download specific target URLs or batch profiles:

```bash
# Download direct URLs
nami download https://www.instagram.com/p/DAEXAMPLE123/ https://x.com/OpenAI/status/123456

# Filter by media kinds (photos, videos, stories, highlights, all)
nami download https://www.instagram.com/example/ --media photos,videos

# Force platform inference when URL is ambiguous
nami download https://x.com/example --platform x --media videos

# Batch download all configured profile files
nami download --profiles

# Filter profile downloads by platform and media kinds
nami download --profiles --platform instagram --media stories,highlights

# Machine-readable JSON output
nami download --profiles --media all --json
```

### `nami doctor`
Inspect system health, engine availability, browser installations, and workspace configuration without network calls:

```bash
nami doctor
nami doctor --json
```

### `nami config`
Inspect and update persistent configuration settings:

```bash
# Show all active settings
nami config show

# Get a specific setting value
nami config get browser
nami config get base_dir

# Set a setting value
nami config set browser chrome
nami config set timeout_seconds 600

# Reset a setting to its default/derived value
nami config unset browser

# Machine-readable JSON output
nami config show --json
```

### `nami archive reset`
Safely manage download tracking archives to enable re-downloading media without deleting archives implicitly:

```bash
# Preview archives that would be reset (dry run)
nami archive reset --all --dry-run

# Back up archives for a specific target (creates timestamped .bak files)
nami archive reset --platform instagram --target example --yes

# Filter reset by media kind
nami archive reset --platform instagram --target example --media stories --yes

# Permanently delete matching archives only when intentional
nami archive reset --all --delete --yes
```

---

## Authentication & Cookies

To access private content, high-resolution stories, or avoid login restrictions:

### 1. Netscape Cookie Files
Place Netscape-formatted cookie files inside your configured `cookies_dir`. Nami validates that files contain at least one valid seven-column Netscape cookie row; placeholder files and headers alone are rejected.

Nami recognizes platform-specific cookie filenames such as:
- `instagram_cookies.txt` or `instagram.com_cookies.txt`
- `tiktok_cookies.txt` or `tiktok.com_cookies.txt`
- `facebook_cookies.txt` or `facebook.com_cookies.txt`
- `x_cookies.txt`, `x.com_cookies.txt`, `twitter_cookies.txt`, or `twitter.com_cookies.txt`

### 2. Browser Session Extraction
TikTok can fall back to browser cookie extraction when no valid cookie file is available. Configure your browser via:
```bash
nami config set browser brave   # Options: brave, chrome, edge, firefox
```
*Note: If the configured browser is currently running, its database may be locked; `nami doctor` will report this as a warning.*

---

## Configuration & Environment Variables

Nami loads configuration in the following order of precedence:
1. Environment variables
2. `~/.nami/nami_config.json`
3. Default values based on the user's home directory

| Configuration Key | Environment Variable | Description | Default |
| :--- | :--- | :--- | :--- |
| `base_dir` | `NAMI_BASE_DIR` | Download output root directory | `~/Nami/downloads` |
| `cookies_dir` | `NAMI_COOKIES_DIR` | Netscape cookie files directory | `~/Nami/cookies` |
| `profiles_dir` | `NAMI_PROFILES_DIR` | Target profile text files directory | `~/Nami/profiles` |
| `browser` | `NAMI_BROWSER` | Browser for automated cookie extraction (`brave`, `chrome`, `edge`, `firefox`) | `brave` |
| `user_agent` | `NAMI_USER_AGENT` | Custom HTTP User-Agent string | Standard Chrome string |
| `timeout_seconds` | `NAMI_TIMEOUT_SECONDS` / `NAMI_TIMEOUT` | Child engine process execution timeout (seconds) | `1800` |
| — | `NAMI_THEME` | Terminal UI theme styling (`dark`, `light`, `auto`) | `dark` |
| — | `NAMI_SKIP_ENV_CHECK` | Set to `1` to bypass startup binary verification | `0` |

---

## Diagnostics

Run local, read-only system diagnostics:

```bash
nami doctor
```

Doctor checks include:
- Configuration validity and integrity
- Python version compatibility (>= 3.10)
- Importability and versions of runtime dependencies (`rich`, `gallery-dl`, `yt-dlp`)
- Workspace readability and writability
- Configured browser installation and process lock state
- Netscape cookie file validity (detects placeholder/empty files)
- Profile file readability and syntax validation
- Potential `urllib3` namespace conflicts
- Stale archive lock detection

---

## Exit Codes

Nami returns deterministic exit codes for CI/CD and scripting pipelines:

| Exit Code | Meaning | Description |
| :---: | :--- | :--- |
| **0** | Success | All requested download or management operations completed successfully |
| **1** | Failure | One or more download operations failed after retry/fallback attempts |
| **2** | Invalid Input | Invalid CLI argument, unparseable profile URL, or corrupt configuration |
| **3** | Partial / Unsupported | Partial results, warnings, or unsupported platform/media combinations |
| **4** | No Results | Extractor completed successfully but found 0 downloadable items |
| **130** | Cancelled | Execution interrupted via `SIGINT` (Ctrl+C) |

---

## Development & Testing

Clone the repository and install development dependencies in an editable environment:

```bash
git clone https://github.com/OpenSelena/nami.git
cd nami
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Running Checks & Tests

```bash
# Run test suite with pytest
PYTHONPATH=src python -m pytest -q

# Run Ruff lint and format checks
python -m ruff check src tests
python -m ruff format --check src tests

# Build and verify distribution package
python -m build
python -m twine check dist/*
check-wheel-contents dist/*.whl
```

The test suite runs completely offline without making external network calls.

---

## Troubleshooting

- **Check diagnostics first**: Run `nami doctor` to get immediate actionable remediation steps.
- **Import issues during testing**: If `pytest` imports an old installed copy of Nami, run with `PYTHONPATH=src` or reinstall editable with `python -m pip install -e ".[dev]"`.
- **Cookie authentication failures**: Ensure exported Netscape cookie files contain genuine 7-column rows and not just headers/comments.
- **Browser database locked**: If TikTok browser cookie extraction fails, close all running instances of your configured browser and retry.
- **Download timeouts**: If downloads of large profiles or playlists time out, increase the timeout limit via `nami config set timeout_seconds 3600`.
- **Re-downloading existing media**: Use `nami archive reset` to clear or back up tracking archives rather than deleting files manually.

---

## License

Distributed under the [MIT License](LICENSE). Developed and maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

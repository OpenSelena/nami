# Nami

An open-source CLI media downloader for Instagram, TikTok, Facebook, and X.

[![CI](https://img.shields.io/github/actions/workflow/status/OpenSelena/nami/ci.yml?branch=main&style=flat-square&logo=github&label=CI)](https://github.com/OpenSelena/nami/actions/workflows/ci.yml)
[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2e7d32.svg?style=flat-square)](LICENSE)

Nami coordinates **`gallery-dl`** and **`yt-dlp`** through a pure functional planning core and deterministic execution shell. It provides deduplicated archive indexing, multi-attempt failure classification, process isolation, and both interactive Rich terminal UI and scriptable JSON CLI modes.

---

## Table of Contents

- [Supported Platforms](#supported-platforms)
- [Architecture & Design Principles](#architecture--design-principles)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Workspace Layout](#workspace-layout)
- [CLI Reference](#cli-reference)
  - [`nami setup`](#nami-setup)
  - [`nami download`](#nami-download)
  - [`nami doctor`](#nami-doctor)
  - [`nami config`](#nami-config)
  - [`nami archive reset`](#nami-archive-reset)
- [Authentication](#authentication)
- [Failure Classification & Retry Policy](#failure-classification--retry-policy)
- [Exit Codes](#exit-codes)
- [Development & Testing](#development--testing)
- [License](#license)

---

## Supported Platforms

| Platform | Photos / Posts | Videos / Reels | Stories | Highlights | Authentication | Primary Engine |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Instagram** | Supported | Supported | Supported | Supported | Netscape Cookie / Anonymous | `gallery-dl` (Photos/Stories) / `yt-dlp` (Video Fallback) |
| **TikTok** | Limited by upstream | Supported | Unsupported | Unsupported | Browser DB / Netscape Cookie | `yt-dlp` / `gallery-dl` |
| **Facebook** | Limited by upstream | Supported | Unsupported | Unsupported | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |
| **X (Twitter)** | Limited by upstream | Supported | Unsupported | Unsupported | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |

*Unsupported media/platform combinations return structured `Outcome.UNSUPPORTED` (Exit Code `3`) rather than silent failure or fake success.*

---

## Architecture & Design Principles

1. **Pure Core, Imperative Shell**:
   - `targets.py`: URL parsing, sanitization, canonical host mapping, and media endpoint expansion.
   - `planner.py`: Pure mapping from `Target` + `MediaKind` to deterministic `PlanStep` sequences without filesystem I/O.
   - `retry.py`: Stateless retry decision engine with exponential jittered backoff.
   - `service.py`: Orchestrator executing plan steps behind atomic file locks (`archive.lock`).
2. **Dual-Engine Routing ([ADR-0001](docs/adr/0001-dual-engine-architecture.md))**:
   - Photos, Instagram stories, and highlights route to `gallery-dl`.
   - Videos route to `gallery-dl` with automatic fallback to `yt-dlp` upon `FailureKind.EXTRACTOR`.
   - Network errors, rate limits, and authentication rejections retry on the same engine without inappropriate cross-engine churn.
3. **No Shell Invocations (`shell=False`)**:
   - All subprocess arguments are passed as discrete string arrays (`argv`) to prevent shell injection.
   - Process trees are tracked and terminated via process group signals (`SIGTERM` / `SIGKILL` on POSIX, `taskkill /PID <PID> /T /F` on Windows).
4. **Strict Path Containment**:
   - Every destination folder is validated against `base_dir` using `safe_target_dir()` to prevent path traversal attacks.

---

## Installation

Requires **Python 3.10 or newer**.

```bash
python -m pip install nami
```

Upgrade to latest release:

```bash
python -m pip install --upgrade nami
```

---

## Quickstart

### 1. Interactive Terminal UI

Run `nami` without arguments:

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

On first launch without configuration, Nami interactively guides setup and workspace initialization.

### 2. Command-Line Direct Invocations

```bash
# Download direct posts
nami download https://www.instagram.com/p/C_EXAMPLE/ https://x.com/OpenAI/status/1234567890

# Filter specific media kinds
nami download https://www.instagram.com/natgeo/ --media photos,videos

# Batch download profiles from configured text files
nami download --profiles --platform instagram --media stories,highlights
```

---

## Workspace Layout

```text
Nami/
├── downloads/
│   ├── instagram/
│   │   └── natgeo/
│   │       ├── Photos/
│   │       │   └── archive.txt
│   │       ├── Videos/
│   │       │   └── archive.txt
│   │       └── Stories/
│   │           └── archive.txt
│   └── tiktok/
│       └── example_user/
│           └── Videos/
├── cookies/
│   ├── instagram_cookies.txt
│   ├── tiktok_cookies.txt
│   ├── facebook_cookies.txt
│   └── x_cookies.txt
└── profiles/
    ├── instagram_profiles.txt
    ├── tiktok_profiles.txt
    ├── facebook_profiles.txt
    └── x_profiles.txt
```

---

## CLI Reference

### `nami setup`

Initializes configuration and workspace directories:

```bash
# Initialize workspace under specific root
nami setup --root /path/to/parent

# Create empty Netscape cookie template files
nami setup --root . --cookie-templates

# Machine-readable JSON output
nami setup --root . --json
```

### `nami download`

Executes download planning and execution for URLs and profile lists:

```bash
nami download [URL ...] [OPTIONS]
```

| Flag | Type | Description |
| :--- | :--- | :--- |
| `URL ...` | Positional | One or more direct content or profile URLs |
| `--profiles` | Flag | Read target URLs from `profiles_dir/<platform>_profiles.txt` |
| `--platform` | Option | Restrict or disambiguate platform (`instagram`, `tiktok`, `facebook`, `x`) |
| `--media` | Option | Comma-separated media kinds (`photos`, `videos`, `stories`, `highlights`, `all`) |
| `--json` | Flag | Output structured JSON result for automated pipelines |

### `nami doctor`

Runs local, read-only diagnostic checks without network I/O:

```bash
nami doctor
nami doctor --json
```

Checks executed:
- Config JSON structure and permissions
- Python version (>= 3.10)
- Core module imports (`rich`, `gallery_dl`, `yt_dlp`)
- Read/write access on `base_dir`, `cookies_dir`, and `profiles_dir`
- Browser installation and process lock check (`brave`, `chrome`, `edge`, `firefox`)
- Netscape cookie file syntax validation (minimum 7 valid columns)
- Profile file accessibility and syntax validation
- Namespace conflicts (`urllib3_future`, `niquests`)
- Stale `archive.lock` files (> 1 hour old)

### `nami config`

Inspects and updates persistent configuration (`~/.nami/nami_config.json`):

```bash
# Display all configuration
nami config show

# Get specific key
nami config get base_dir
nami config get browser

# Set key
nami config set browser chrome
nami config set timeout_seconds 3600

# Reset key to default
nami config unset browser

# JSON mode
nami config show --json
```

### `nami archive reset`

Manages download tracking records (`archive.txt`) safely:

```bash
# Dry run preview
nami archive reset --all --dry-run

# Back up archives for target (creates .bak files)
nami archive reset --platform instagram --target natgeo --yes

# Reset specific media kind
nami archive reset --platform instagram --target natgeo --media stories --yes

# Delete matching archives permanently
nami archive reset --platform tiktok --target creator --delete --yes
```

---

## Authentication

### Netscape Cookie Files
Export cookies from your browser using a Netscape-compatible extension and save them into `cookies_dir`:
- `instagram_cookies.txt` or `instagram.com_cookies.txt`
- `tiktok_cookies.txt` or `tiktok.com_cookies.txt`
- `facebook_cookies.txt` or `facebook.com_cookies.txt`
- `x_cookies.txt`, `x.com_cookies.txt`, or `twitter_cookies.txt`

Nami validates that cookie files contain valid 7-column rows before passing them to engines.

### Browser Cookie DB
When downloading from TikTok without an explicit cookie file, Nami attempts direct cookie extraction from the configured browser (`brave`, `chrome`, `edge`, `firefox`).

---

## Failure Classification & Retry Policy

`failures.py` maps error logs to typed `FailureKind` categories:

| Failure Kind | Description | Retry Action |
| :--- | :--- | :--- |
| `FailureKind.AUTH` | HTTP 401, login required | 1 anonymous retry if credentials were supplied |
| `FailureKind.COOKIE` | Cookie decryption or file error | 1 anonymous retry if credentials were supplied |
| `FailureKind.RATE_LIMIT` | HTTP 429, too many requests | Stop immediately (no retry) |
| `FailureKind.NETWORK` | DNS reset, SSL, connection timeout | Up to 3 attempts with exponential jittered backoff |
| `FailureKind.EXTRACTOR` | Unsupported route, broken extractor | 1 retry on alternate engine (`yt-dlp`) |
| `FailureKind.NOT_FOUND` | HTTP 404, account deleted | Stop immediately (`Outcome.NO_RESULTS`) |
| `FailureKind.DEPENDENCY` | Missing binary or module | Stop immediately |
| `FailureKind.TIMEOUT` | Subprocess deadline exceeded | Up to 3 attempts with backoff |
| `FailureKind.LOCKED` | Checkpoint or archive lock busy | Stop immediately |

---

## Exit Codes

| Code | Outcome | Description |
| :---: | :--- | :--- |
| **`0`** | `SUCCESS` | All items downloaded or already up to date |
| **`1`** | `FAILED` | Unrecoverable failure across attempts |
| **`2`** | `INVALID` | Malformed CLI arguments, invalid target URLs, or corrupt config |
| **`3`** | `PARTIAL / WARN` | Mixed batch outcomes, unsupported operations, or doctor warnings |
| **`4`** | `NO_RESULTS` | Extractor ran cleanly but found zero downloadable items |
| **`130`** | `CANCELLED` | Execution interrupted via `SIGINT` (Ctrl+C) |

---

## Development & Testing

### Setup Environment

```bash
git clone https://github.com/OpenSelena/nami.git
cd nami
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Running Test Suite

```bash
# Run pytest
python -m pytest

# Run Ruff linter and formatter
python -m ruff check src tests
python -m ruff format --check src tests

# Build distribution package
python -m build
```

---

## License

Distributed under the [MIT License](LICENSE). Maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

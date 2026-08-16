<div align="center">

# 🌊 Nami

### *An open-source CLI media downloader for Instagram, TikTok, Facebook, and X*

[![CI](https://img.shields.io/github/actions/workflow/status/OpenSelena/nami/ci.yml?branch=main&style=for-the-badge&logo=github&label=CI)](https://github.com/OpenSelena/nami/actions/workflows/ci.yml)
[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2e7d32.svg?style=for-the-badge)](LICENSE)

<p align="center">
  <b>Nami</b> is a high-performance, modular CLI and interactive media downloader for Instagram, TikTok, Facebook, and X (Twitter). Powered by <b>gallery-dl</b> and <b>yt-dlp</b> engines with a modern <b>Rich terminal UI</b>, Nami provides dual-engine fallback, anti-duplicate archiving, automated cookie management, health doctor diagnostics, and machine-readable JSON workflows.
</p>

[Installation](#installation) • [Quickstart](#quickstart) • [CLI Commands](#cli-commands-reference) • [Platform Matrix](#supported-platforms) • [Configuration](#configuration--environment-variables) • [Development](#development--testing)

</div>

---

## Features

- **Multi-Platform Batch Downloads**: Extract high-resolution photos, videos, reels, posts, stories, and highlights.
- **Dual-Engine Architecture**: Intelligently routes tasks between `gallery-dl` and `yt-dlp` with automatic fallback on extractor failures.
- **Interactive & Headless Modes**: Run interactively with an intuitive terminal UI or integrate into headless pipelines with dedicated CLI subcommands and `--json` output.
- **Smart Anti-Duplicate Archiving**: Maintains per-target `archive.txt` records to avoid redundant re-downloads, with safe `archive reset` management.
- **Flexible Authentication**: Supports Netscape cookie files, anonymous fallbacks, and direct browser cookie extraction (`--cookies-from-browser`).
- **Resilient Retry Policy**: Exponential jittered backoff for transient network errors, immediate rate-limit handling, and process isolation.
- **Built-in Doctor**: Run `nami doctor` to verify local binaries, browser installations, cookie permissions, and workspace health.

---

## Supported Platforms

| Platform | Photos | Videos / Reels | Stories | Highlights | Auth Support | Primary Engine |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Instagram** | Included | Included | Included | Included | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |
| **TikTok** | Included | Included | N/A | N/A | Browser DB / Netscape Cookie | `yt-dlp` / `gallery-dl` |
| **Facebook** | Included | Included | N/A | N/A | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |
| **X (Twitter)** | Included | Included | N/A | N/A | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |

---

## Installation

Install `nami` via `pip`:

```bash
pip install nami
```

*Dependencies (`rich`, `gallery-dl`, `yt-dlp`) are automatically installed.*

To upgrade to the latest version:

```bash
pip install -U nami
```

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
│ 1  Photos only                                       │
│ 2  Videos only                                       │
│ 3  Stories only                                      │
│ 4  Highlights only                                   │
│ 5  Photos + Videos                                   │
│ 6  Stories + Highlights                              │
│ 7  All                                               │
│ 8  Settings                                          │
│ 0  Exit                                              │
└──────────────────────────────────────────────────────┘
```

On first launch, Nami guides you through workspace initialization.

### 2. Workspace Layout
Nami organizes downloads, cookie files, and target profile lists cleanly:

```text
Nami/
├── downloads/      # Extracted media organized by platform, account & kind
├── cookies/        # Optional Netscape cookie files (*_cookies.txt)
└── profiles/       # Target profile URLs (*_profiles.txt)
```

---

## CLI Commands Reference

Nami provides a full suite of scriptable subcommands for headless and automated pipelines:

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

# Batch download all configured profile files
nami download --profiles

# Filter by platform and specific media kinds
nami download --profiles --platform instagram --media stories,highlights
nami download https://www.tiktok.com/@creator --media videos

# Machine-readable JSON output
nami download --profiles --json
```

*Media kinds options:* `photos`, `videos`, `stories`, `highlights`, `all` (or comma-separated list).

### `nami doctor`
Inspect system health, engine availability, browser installations, and workspace configuration:

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
```

*Configurable keys:* `base_dir`, `cookies_dir`, `profiles_dir`, `browser`, `user_agent`, `timeout_seconds`.

### `nami archive reset`
Safely manage download tracking archives to enable re-downloading media:

```bash
# Preview archives that would be reset
nami archive reset --platform instagram --dry-run

# Back up archives for a specific profile (creates timestamped .bak)
nami archive reset --platform instagram --target nasa --yes

# Reset all archives permanently
nami archive reset --all --delete --yes
```

---

## Authentication & Cookies

To access private content, high-resolution stories, or avoid login walls:

1. **Netscape Cookie Files**: Place cookie text files inside your configured `cookies_dir`:
   - `instagram.com_cookies.txt` (or `instagram_cookies.txt`)
   - `facebook.com_cookies.txt` (or `facebook_cookies.txt`)
   - `x.com_cookies.txt` (or `x_cookies.txt`, `twitter.com_cookies.txt`)
   - `tiktok.com_cookies.txt` (or `tiktok_cookies.txt`)
2. **Browser Extraction**: Set `browser` (`brave`, `chrome`, `edge`, `firefox`) via `nami config set browser <name>` or `NAMI_BROWSER` environment variable.

---

## Configuration & Environment Variables

Settings are saved in `~/.nami/nami_config.json`. You can override defaults using environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NAMI_BASE_DIR` | Custom output downloads directory path | `~/Nami/downloads` |
| `NAMI_COOKIES_DIR` | Custom Netscape cookie directory path | `~/Nami/cookies` |
| `NAMI_PROFILES_DIR` | Custom profile text files directory path | `~/Nami/profiles` |
| `NAMI_BROWSER` | Browser for automated cookie extraction (`brave`, `chrome`, `edge`, `firefox`) | `brave` |
| `NAMI_USER_AGENT` | Custom HTTP User-Agent string | Standard Chrome string |
| `NAMI_TIMEOUT_SECONDS` | Child engine process execution timeout in seconds | `900` |
| `NAMI_THEME` | Terminal UI theme (`dark` or `light`) | `dark` |
| `NAMI_SKIP_ENV_CHECK` | Set to `1` to bypass startup binary presence check | `0` |

---

## Development & Testing

Clone the repository and install dev dependencies:

```bash
git clone https://github.com/OpenSelena/nami.git
cd nami
pip install -e ".[dev]"
```

Run test suite and quality checks:

```bash
# Run pytest
pytest

# Run Ruff linter and formatter checks
ruff check src tests
ruff format --check src tests

# Build and verify distribution package
python -m build
twine check dist/*
check-wheel-contents dist/*.whl
```

---

## License

Distributed under the [MIT License](LICENSE). Developed and maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

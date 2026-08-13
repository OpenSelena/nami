<div align="center">

# 🌊 Nami

### *An open-source CLI media downloader for Instagram, TikTok, Facebook, and X*

[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=for-the-badge)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![License](https://img.shields.io/pypi/l/nami?style=for-the-badge&color=2e7d32)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/OpenSelena/nami?style=for-the-badge&color=D97757)](https://github.com/OpenSelena/nami)

<p align="center">
  <b>Nami</b> is a lightweight, open-source media archiver designed for seamless multi-platform media extraction. Combining <b>gallery-dl</b> (primary gallery/archiving engine) and <b>yt-dlp</b> (video/specialized engine) with an interactive <b>Rich terminal interface</b>, Nami orchestrates two powerful extraction engines with deterministic fallback rules, deduplication, and secure authentication.
</p>

[Installation](#installation) • [Usage Flow](#usage-flow) • [Extractor Architecture](#extractor-architecture) • [Supported Platforms](#supported-platforms) • [Directory Layout](#1-project-workspace-initializer) • [Configuration](#configuration)

</div>

---

## Features

- **2-Engine Architecture**: Powered by `gallery-dl` and `yt-dlp` with deterministic capability mapping.
- **Instagram Gallery-DL Archiving**: Uses `gallery-dl` as the primary extraction engine for Instagram profiles, photos, videos, reels, stories, and highlights.
- **Video & Fallback Engine**: Uses `yt-dlp` as the primary video engine for TikTok, Facebook, and X, and controlled fallback for Instagram videos/reels.
- **Failure-Aware Fallback Policy**: Automatic engine fallback is allowed **only** for `EXTRACTOR` and `UNSUPPORTED` errors. Rate limits (`429`), authentication errors, and network failures halt safely without hammering platforms.
- **Smart Deduplication & Archive Safety**: Historical download state in `archive.txt` is preserved and never automatically deleted when media directories are emptied.
- **Authentication Security**: Supports Netscape cookie files (`<platform>.com_cookies.txt`) and browser cookies. Credentials are strictly masked from logs.
- **Terminal UI**: Powered by `rich` with explicit status indicators (`✓ downloaded`, `⚠ Rate limited`, `✗ Failed`, `N/A Unsupported`).

---

## Extractor Architecture

```text
                         ┌─────────────────────┐
                         │       NAMI CLI      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Platform Router   │
                         └──────────┬──────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             ▼                      ▼                      ▼
       Instagram                  TikTok               Facebook / X
             │                      │                      │
             ▼                      ▼                      ▼
       Extraction Plan        Extraction Plan        Extraction Plan
             │                      │                      │
             ▼                      ▼                      ▼
       Extractor Manager       Extractor Manager      Extractor Manager
             │                      │                      │
         ┌───┴───┐              ┌───┴───┐              ┌───┴───┐
         ▼       ▼              ▼       ▼              ▼       ▼
        GD     YTDLP          YTDLP    GD            YTDLP    GD
         │       │
         └───┬───┘
             ▼
      Failure Classifier
             │
      ┌──────┼─────────┐
      ▼      ▼         ▼
    Retry  Fallback   Stop
```

### Engine Assignment

- **Instagram**: `gallery-dl` (Primary) $\rightarrow$ `yt-dlp` (Controlled Video Fallback)
- **TikTok**: `yt-dlp` (Primary) $\rightarrow$ `gallery-dl` (Fallback)
- **Facebook**: `yt-dlp` (Primary) $\rightarrow$ `gallery-dl` (Fallback)
- **X (Twitter)**: `yt-dlp` (Primary) $\rightarrow$ `gallery-dl` (Fallback)

---

## Supported Platforms

| Platform | Photos | Videos | Stories | Highlights | Extractor Engines | Authentication Mode |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Instagram** | Included | Included | Included | Included | gallery-dl / yt-dlp | Netscape Cookie / Anonymous |
| **TikTok** | Included | Included | N/A | N/A | yt-dlp / gallery-dl | Browser DB / Netscape Cookie |
| **Facebook** | Included | Included | N/A | N/A | yt-dlp / gallery-dl | Netscape Cookie / Anonymous |
| **X (Twitter)** | Included | Included | N/A | N/A | yt-dlp / gallery-dl | Netscape Cookie / Anonymous |

---

## Installation

Install `nami` directly via `pip`:

```bash
pip install nami
```

*All extraction engines (`gallery-dl`, `yt-dlp`) and `rich` are automatically installed.*

To upgrade to the latest release:

```bash
pip install -U --no-cache-dir nami
```

---

## Usage Flow

### 1. Project Workspace Initializer
When you launch `nami` for the first time, it automatically creates your local workspace structure:

```text
Nami/
├── downloads/      # Extracted media organized by platform & account
├── cookies/        # Netscape cookie files (*_cookies.txt)
└── profiles/       # Target account URL text files (*_profiles.txt)
```

### 2. Configure Profile Sources
Add your target account URLs into the designated text files inside `Nami/profiles/`:

```text
Nami/profiles/
├── instagram_profiles.txt  # Add Instagram profile URLs (one per line)
├── tiktok_profiles.txt     # Add TikTok profile URLs
├── facebook_profiles.txt   # Add Facebook profile URLs
└── x_profiles.txt          # Add X / Twitter profile URLs
```

### 3. Session Authentication
Place Netscape-formatted cookie files inside `Nami/cookies/`:
- `instagram.com_cookies.txt` (Netscape cookie file)
- `facebook.com_cookies.txt`
- `x.com_cookies.txt`

### 4. Interactive Execution & Filtering
Launch the application to run batch downloads across your configured profile lists:

```bash
nami
```

---

## Troubleshooting

- **HTTP 429 Rate Limit**: Nami automatically halts cleanly without hammering platforms with multiple extractors. Wait a few minutes before retrying.
- **urllib3 namespace conflicts**: Run `python -m pip install -U nami gallery-dl yt-dlp urllib3` to align dependencies.
- **Missing Cookie File**: Ensure Netscape cookie files are placed in `<workspace>/Nami/cookies/` and match the expected naming format (`<platform>.com_cookies.txt`).

---

## Privacy & Security

- **No Passwords Stored**: Passwords are never logged or stored in `nami_config.json`.
- **Log Masking**: Sensitive session tokens, raw cookies, and authentication headers are masked from debug logs.
- **File Permissions**: Secure permissions (`0600` for files, `0700` for directories) are applied on Unix systems.

---

## License

Distributed under the [MIT License](LICENSE). Developed and maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

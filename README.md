<div align="center">

# 🌊 Nami

### *An open-source CLI media downloader for Instagram, TikTok, Facebook, and X*

[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=for-the-badge)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![License](https://img.shields.io/pypi/l/nami?style=for-the-badge&color=2e7d32)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/OpenSelena/nami?style=for-the-badge&color=D97757)](https://github.com/OpenSelena/nami)

<p align="center">
  <b>Nami</b> is a lightweight, open-source media archiver designed for seamless multi-platform media extraction. Combining <b>Instaloader</b>, <b>gallery-dl</b>, and <b>yt-dlp</b> with an interactive <b>Rich terminal interface</b>, Nami orchestrates three specialized extraction engines with deterministic fallback rules, deduplication, and secure authentication.
</p>

[Installation](#installation) • [Usage Flow](#usage-flow) • [Extractor Architecture](#extractor-architecture) • [Supported Platforms](#supported-platforms) • [Directory Layout](#1-project-workspace-initializer) • [Configuration](#configuration)

</div>

---

## Features

- **Multi-Engine Orchestration**: Orchestrates `Instaloader`, `gallery-dl`, and `yt-dlp` simultaneously with deterministic capabilities.
- **Instagram Primary & Fallback Strategy**: Uses Python-native `Instaloader` as the primary engine for Instagram profiles, posts, reels, stories, and highlights, with `gallery-dl` and `yt-dlp` as deterministic fallbacks.
- **Non-Instagram Engines**: Uses `yt-dlp` (primary video engine) and `gallery-dl` (fallback/gallery engine) for TikTok, Facebook, and X.
- **Failure-Aware Fallback**: Fallbacks are triggered only for capability/extractor errors. Rate limits (`429`) and network errors use backoff without stripping cookies or switching engines.
- **Smart Deduplication & Archive Safety**: Historical download state in `archive.txt` is preserved and never automatically deleted when media directories are emptied.
- **Authentication Security**: Supports Netscape cookie files, browser cookie extraction, and Instaloader sessions. Credentials and cookies are strictly masked from logs.
- **Terminal UI**: Powered by `rich` with customizable contrast themes (`light` / `dark`).

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
        ┌────┼────┐            ┌────┴────┐             ┌──┴────┐
        ▼    ▼    ▼            ▼         ▼             ▼       ▼
     Insta  GD   YTDLP        YTDLP      GD           YTDLP    GD
   loader
        │    │    │
        └────┼────┘
             ▼
      Failure Classifier
             │
      ┌──────┼─────────┐
      ▼      ▼         ▼
    Retry  Fallback   Stop
```

### Engine Assignment

- **Instagram**: `Instaloader` (Primary) $\rightarrow$ `gallery-dl` / `yt-dlp` (Fallback)
- **TikTok**: `yt-dlp` (Primary) $\rightarrow$ `gallery-dl` (Fallback)
- **Facebook**: `yt-dlp` (Primary) $\rightarrow$ `gallery-dl` (Fallback)
- **X (Twitter)**: `yt-dlp` (Primary) $\rightarrow$ `gallery-dl` (Fallback)

---

## Supported Platforms

| Platform | Photos | Videos | Stories | Highlights | Extractor Engines | Authentication Mode |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Instagram** | Included | Included | Included | Included | Instaloader / gallery-dl / yt-dlp | Session File / Netscape Cookie / Anonymous |
| **TikTok** | Included | Included | N/A | N/A | yt-dlp / gallery-dl | Browser DB / Netscape Cookie |
| **Facebook** | Included | Included | N/A | N/A | yt-dlp / gallery-dl | Netscape Cookie / Anonymous |
| **X (Twitter)** | Included | Included | N/A | N/A | yt-dlp / gallery-dl | Netscape Cookie / Anonymous |

---

## Installation

Install `nami` directly via `pip`:

```bash
pip install nami
```

*All extraction engines (`instaloader`, `gallery-dl`, `yt-dlp`) and `rich` are automatically installed.*

To upgrade to the latest release:

```bash
pip install -U nami
```

---

## Usage Flow

### 1. Project Workspace Initializer
When you launch `nami` for the first time, it automatically creates your local workspace structure:

```text
Nami/
├── downloads/      # Extracted media organized by platform & account
├── cookies/        # Netscape cookie files (*_cookies.txt) & Instaloader session files (session-*)
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
Place Netscape-formatted cookie files or Instaloader session files inside `Nami/cookies/`:
- `session-<username>` (Instaloader session file)
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

- **HTTP 429 Rate Limit**: Nami automatically enters backoff retry without stripping cookies or switching engines. If rate limited, wait a few minutes before retrying.
- **urllib3 namespace conflicts**: Run `python -m pip install -U nami gallery-dl yt-dlp instaloader urllib3` to align dependencies.
- **Missing Session / Cookie File**: Ensure cookie files are placed in `<workspace>/Nami/cookies/` and match the expected naming format (`<platform>.com_cookies.txt` or `session-<username>`).

---

## Privacy & Security

- **No Passwords Stored**: Passwords are never logged or stored in `nami_config.json`.
- **Log Masking**: Sensitive session tokens, raw cookies, and authentication headers are masked from debug logs.
- **File Permissions**: Secure permissions (`0600` for files, `0700` for directories) are applied on Unix systems.

---

## License

Distributed under the [MIT License](LICENSE). Developed and maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

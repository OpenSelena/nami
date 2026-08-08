<div align="center">

# 🌊 Nami

### *An open-source CLI media downloader for Instagram, TikTok, Facebook, and X*

[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=for-the-badge)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![License](https://img.shields.io/pypi/l/nami?style=for-the-badge&color=2e7d32)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/OpenSelena/nami?style=for-the-badge&color=D97757)](https://github.com/OpenSelena/nami)

<p align="center">
  <b>Nami</b> is a lightweight, open-source media downloader designed for seamless batch extraction across social platforms. Combining <b>gallery-dl</b> and <b>yt-dlp</b> with an interactive <b>Rich terminal interface</b>, Nami automates deduplication, rate-limit retries, and browser cookie handling.
</p>

[Installation](#installation) • [Usage Flow](#usage-flow) • [Supported Platforms](#supported-platforms) • [Directory Layout](#1-project-workspace-initializer) • [Configuration](#configuration)

</div>

---

## Features

- **Photos & Videos**: Batch download high-resolution photos, reels, videos, and posts.
- **Instagram Stories & Highlights**: Extract stories and highlight archives automatically.
- **Smart Anti-Duplicate Archiving**: Automatic `archive.txt` tracking avoids re-downloading existing media.
- **Automated Cookie Integration**: Supports Netscape cookie files and browser session extraction (`--cookies-from-browser`).
- **Cookie Fallback & Retry Logic**: Automatically attempts anonymous fallbacks and handles rate-limits gracefully.
- **Terminal UI**: Powered by `rich` with customizable contrast themes (`light` / `dark`).

---

## Supported Platforms

| Platform | Photos | Videos | Stories | Highlights | Authentication Mode | Status |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **Instagram** | Included | Included | Included | Included | Netscape Cookie / Anonymous | Active |
| **TikTok** | Included | Included | N/A | N/A | Browser DB / Netscape Cookie | Active |
| **Facebook** | Included | Included | N/A | N/A | Netscape Cookie / Anonymous | Active |
| **X (Twitter)** | Included | Included | N/A | N/A | Netscape Cookie / Anonymous | Active |

---

## Installation

Install `nami` directly via `pip`:

```bash
pip install nami
```

*All dependencies (`rich`, `gallery-dl`, `yt-dlp`) are automatically installed.*

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
├── cookies/        # Optional Netscape cookie files (*_cookies.txt)
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
Place Netscape-formatted cookie files inside `Nami/cookies/` to download private content or bypass login restrictions:
- `instagram.com_cookies.txt`
- `facebook.com_cookies.txt`
- `x.com_cookies.txt`

### 4. Interactive Execution & Filtering
Launch the application to run batch downloads across your configured profile lists:

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

---

## Configuration & Environment Variables

User settings are saved automatically in `~/.nami/nami_config.json`. You can also configure Nami via environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NAMI_THEME` | Terminal theme styling (`dark` or `light`) | `dark` |
| `NAMI_BASE_DIR` | Custom output downloads directory path | Configured path |
| `NAMI_COOKIES_DIR` | Custom Netscape cookie directory path | Configured path |
| `NAMI_PROFILES_DIR` | Custom profile text files directory path | Configured path |
| `NAMI_BROWSER` | Browser for automated cookie extraction (`brave`, `chrome`, `edge`, `firefox`) | `brave` |
| `NAMI_USER_AGENT` | Custom HTTP User-Agent string for request headers | Chrome 131 standard string |
| `NAMI_SKIP_ENV_CHECK` | Set to `1` to skip initial dependency verification | `0` |

### Customizing Theme Contrast
Adjust terminal theme styling by setting `NAMI_THEME`:

```bash
# Light Terminal Theme
export NAMI_THEME=light

# Dark Terminal Theme (Default)
export NAMI_THEME=dark
```

---

## License

Distributed under the [MIT License](LICENSE). Developed and maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

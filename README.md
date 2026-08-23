<div align="center">

# Nami

**Deterministic media downloader for Instagram, TikTok, Facebook, and X**

[![CI](https://img.shields.io/github/actions/workflow/status/OpenSelena/nami/ci.yml?branch=main&style=flat-square&logo=github&label=CI&color=2ea44f)](https://github.com/OpenSelena/nami/actions/workflows/ci.yml)
[![PyPI Version](https://img.shields.io/pypi/v/nami.svg?color=D97757&style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/nami/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-0969da?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/nami/)
[![Architecture](https://img.shields.io/badge/architecture-dual--engine-6f42c1?style=flat-square)](docs/adr/0001-dual-engine-architecture.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-2e7d32.svg?style=flat-square)](LICENSE)

</div>

Nami coordinates **gallery-dl** and **yt-dlp** through a pure functional planning core and isolated execution shell. Engineered for batch extraction, atomic deduplication, classified retry loops, and headless pipelines.

[Platform Matrix](#platform-support-matrix) · [Architecture](#architecture) · [Installation](#installation) · [Quickstart](#quickstart) · [CLI Reference](#cli-reference) · [Configuration](#configuration--environment-variables) · [Diagnostics](#system-diagnostics)

---

## Architecture

Nami separates pure domain logic from side effects using narrow module seams.

<table>
<tr>
<td width="50%">

**Dual-Engine Routing** — Directs photos, stories, and highlights to `gallery-dl` and routes videos to `gallery-dl` with automatic extractor fallback to `yt-dlp` ([ADR-0001](docs/adr/0001-dual-engine-architecture.md)).

</td>
<td width="50%">

**Atomic Containment & Locking** — Per-target PID-keyed `archive.lock` blocks concurrent process contention. Strict `safe_target_dir` prevents path traversal and drive escapes.

</td>
</tr>
<tr>
<td width="50%">

**Pure Functional Planning** — Planning core converts inputs to deterministic `PlanStep` sequences without disk or network I/O, enabling offline unit testing in <0.2s.

</td>
<td width="50%">

**Universal Invocation** — Run interactively via Rich terminal UI or headlessly in CI/CD automation using `nami` or `python -m nami` with structured `--json` stdout.

</td>
</tr>
</table>

### Data flow

```mermaid
flowchart TD
    subgraph Core ["Pure Domain Core (No Side Effects)"]
        A[Target URLs / Profiles] -->|parse_target| B[targets.py]
        B -->|build_plan| C[planner.py]
    end

    subgraph Shell ["Stateful Imperative Shell"]
        D{NamiService Orchestrator}
        D -->|Lock Archive| E[archive.py]
        D -->|Execute Command| F[process.py]
        F --> G[gallery-dl / yt-dlp]
        F -->|Capture Output| H[failures.py]
        H -->|Evaluate Decision| I[retry.py]
    end

    C --> D
    D --> J[BatchResult: Exit Code & JSON]
```

### Module seams

| Module | Public interface | Encapsulated complexity |
| :--- | :--- | :--- |
| [`targets.py`](src/nami/targets.py) | `parse_target()`, `safe_target_dir()`, `resolve_target_endpoints()` | URL regex decomposition, host mapping, path traversal prevention, endpoint derivation |
| [`planner.py`](src/nami/planner.py) | `build_plan(DownloadRequest) -> tuple[PlanStep, ...]` | Side-effect-free step generation, media kind expansion, destination path mapping |
| [`archive.py`](src/nami/archive.py) | `ArchiveLock`, `discover_archives()`, `reset_archives()` | Non-blocking PID-keyed locking, stale lock identification, `.bak` file generation |
| [`process.py`](src/nami/process.py) | `SubprocessRunner.run(CommandSpec) -> CommandResult` | Zero-shell execution (`shell=False`), credential sanitization, cross-platform process tree termination |
| [`failures.py`](src/nami/failures.py) | `classify_failure()`, `failure_message()` | Error stream parsing, diagnostic precedence ranking, typed `FailureKind` categorization |
| [`retry.py`](src/nami/retry.py) | `RetryPolicy.decide() -> RetryDecision` | Bounded exponential backoff with deterministic pseudo-random jitter |

---

## Platform Support Matrix

| Platform | Photos & Posts | Videos & Reels | Stories | Highlights | Authentication | Primary Backend |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Instagram** | Supported | Supported | Supported | Supported | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` (Fallback) |
| **TikTok** | Limited | Supported | — | — | Browser DB / Netscape Cookie | `yt-dlp` / `gallery-dl` |
| **Facebook** | Limited | Supported | — | — | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |
| **X (Twitter)** | Limited | Supported | — | — | Netscape Cookie / Anonymous | `gallery-dl` / `yt-dlp` |

> [!NOTE]
> Unsupported platform/media combinations return structured `Outcome.UNSUPPORTED` records and exit with status `3`.

---

## Installation

Requires **Python 3.10 or newer**.

```bash
# Install from PyPI
python -m pip install nami

# Upgrade existing install
python -m pip install --upgrade --no-cache-dir nami
```

---

## Quickstart

### Initialize workspace & PATH

Run workspace setup once (auto-configures download directories and registers `nami` on system `PATH`):

```bash
python -m nami setup --root ~
```

### Interactive mode

Run `nami`:

```bash
nami
```

```
╭─ Nami ───────────────────────────────────────────────────────────── v5.0.6 ─╮
│ What do you want to download?                                               │
│                                                                             │
│  1  Photos only                                                             │
│  2  Videos only                                                             │
│  3  Stories only                                                            │
│  4  Highlights only                                                         │
│  5  Photos + Videos                                                         │
│  6  Stories + Highlights                                                    │
│  7  All                                                                     │
│  8  Settings                                                                │
│  0  Exit                                                                    │
│                                                                             │
│  Save: ~/Nami/downloads                                                     │
╰─────────────────────────────────────────────────────────────────────────────╯
```

### CLI batch invocations

```bash
# Download direct posts and reels
nami download https://www.instagram.com/p/C_EXAMPLE/ https://x.com/OpenAI/status/1234567890

# Target specific profile media
nami download https://www.instagram.com/natgeo/ --media photos,videos

# Headless batch processing with JSON stdout
nami download --profiles --platform instagram --media all --json
```

---

## Workspace layout

```
Nami/
├── downloads/                     # Output directory organized by platform & account
│   ├── instagram/
│   │   └── natgeo/
│   │       ├── Photos/
│   │       │   └── archive.txt    # Deduplication ledger
│   │       ├── Videos/
│   │       │   └── archive.txt
│   │       └── Stories/
│   │           └── archive.txt
│   └── tiktok/
│       └── example_user/
│           └── Videos/
│               └── archive.txt
├── cookies/                       # Netscape-format cookie files
│   ├── instagram_cookies.txt
│   ├── tiktok_cookies.txt
│   ├── facebook_cookies.txt
│   └── x_cookies.txt
└── profiles/                      # Target profile lists
    ├── instagram_profiles.txt
    ├── tiktok_profiles.txt
    ├── facebook_profiles.txt
    └── x_profiles.txt
```

---

## CLI Reference

### `nami download`

Plan and execute downloads for individual URLs or profile lists.

```bash
nami download [URL ...] [OPTIONS]
```

| Flag | Type | Description |
| :--- | :--- | :--- |
| `URL ...` | Positional | One or more content or profile URLs |
| `--profiles` | Flag | Batch download all targets listed in `profiles_dir` |
| `--platform` | Option | Disambiguate platform (`instagram`, `tiktok`, `facebook`, `x`) |
| `--media` | Option | Comma-separated kinds: `photos`, `videos`, `stories`, `highlights`, `all` |
| `--json` | Flag | Output structured JSON result for automated pipelines |

### `nami setup`

Initialize directory layout and write configuration.

```bash
nami setup [OPTIONS]
```

| Flag | Type | Description |
| :--- | :--- | :--- |
| `--root <PATH>` | Option | Target parent directory for the workspace |
| `--cookie-templates` | Flag | Create empty Netscape cookie templates in `cookies/` |
| `--json` | Flag | Output initialization result as JSON |

### `nami doctor`

Run read-only system diagnostic checks without network access.

```bash
nami doctor [OPTIONS]
```

| Flag | Type | Description |
| :--- | :--- | :--- |
| `--json` | Flag | Output structured health checks and remediation steps in JSON |

Example output:

```
PASS  config: Configuration loaded successfully
PASS  python: Python 3.14.7 (>= 3.10 required)
PASS  dependencies: All required packages are installed
PASS  workspace: Base directory is writable
PASS  browser: Brave is installed and unlocked
PASS  cookies: Netscape cookies valid
PASS  urllib3: Clean namespace (no conflicts)
PASS  archive_locks: No stale locks detected
```

### `nami config`

Manage persistent settings in `~/.nami/nami_config.json`.

```bash
nami config show [--json]
nami config get <KEY> [--json]
nami config set <KEY> <VALUE> [--json]
nami config unset <KEY> [--json]
```

| Key | Valid Values | Description |
| :--- | :--- | :--- |
| `base_dir` | Path string | Root directory for downloaded media |
| `cookies_dir` | Path string | Directory containing Netscape cookie files |
| `profiles_dir` | Path string | Directory containing `*_profiles.txt` lists |
| `browser` | `brave`, `chrome`, `edge`, `firefox` | Browser for automated cookie extraction |
| `user_agent` | String | HTTP User-Agent header passed to child engines |
| `timeout_seconds` | Integer (`> 0`) | Subprocess execution deadline in seconds |

### `nami archive reset`

Manage download tracking records (`archive.txt`) safely without data loss.

```bash
nami archive reset [OPTIONS]
```

| Flag | Type | Description |
| :--- | :--- | :--- |
| `--all` | Flag | Target all archives across all platforms |
| `--platform <NAME>` | Option | Filter archives by platform |
| `--target <KEY>` | Option | Filter archives by target account |
| `--media <KIND>` | Option | Filter archives by media kind |
| `--dry-run` | Flag | Preview affected archives without modifying disk |
| `--delete` | Flag | Permanently delete matching archives (default: creates `.bak`) |
| `--yes` | Flag | Confirm action without interactive prompt |
| `--json` | Flag | Output affected archive paths in JSON |

---

## Authentication & Cookies

### Netscape cookie files

Save exported cookies into `cookies_dir`. Nami verifies that files contain genuine 7-column rows before passing them to child engines:

- `instagram_cookies.txt` or `instagram.com_cookies.txt`
- `tiktok_cookies.txt` or `tiktok.com_cookies.txt`
- `facebook_cookies.txt` or `facebook.com_cookies.txt`
- `x_cookies.txt` or `x.com_cookies.txt`

### Browser database extraction

For TikTok downloads without a cookie file, Nami extracts session tokens from local browser databases (`brave`, `chrome`, `edge`, `firefox`).

---

## Failure Taxonomy & Recovery Matrix

`failures.py` maps subprocess output to deterministic `FailureKind` categories:

| Failure Kind | Diagnostic Indicator | Recovery Strategy |
| :--- | :--- | :--- |
| `AUTH` | HTTP 401, login required | 1 anonymous retry if credentials were provided |
| `COOKIE` | Corrupt or undecryptable cookie file | 1 anonymous retry if credentials were provided |
| `RATE_LIMIT` | HTTP 429, temporary platform throttle | Stop immediately without cross-engine churn |
| `NETWORK` | Connection reset, TLS error, DNS timeout | Up to 3 attempts with exponential jittered backoff |
| `EXTRACTOR` | Route failure, extractor deprecation | 1 retry on alternate engine (`yt-dlp`) |
| `NOT_FOUND` | HTTP 404, account deleted, private media | Stop immediately with `Outcome.NO_RESULTS` |
| `DEPENDENCY` | Missing binary or unimportable module | Stop immediately |
| `TIMEOUT` | Subprocess deadline exceeded | Up to 3 attempts with exponential backoff |
| `LOCKED` | Archive lock contention or account challenge | Stop immediately |

---

## Deterministic Exit Codes

| Code | Outcome | Meaning |
| :---: | :--- | :--- |
| `0` | `SUCCESS` | All operations downloaded or already up to date |
| `1` | `FAILED` | Unrecoverable error occurred on one or more operations |
| `2` | `INVALID` | Malformed CLI syntax, invalid URL, or corrupted configuration |
| `3` | `PARTIAL` | Mixed outcomes, unsupported operations, or doctor warnings |
| `4` | `NO_RESULTS` | Extractor completed successfully but found zero downloadable items |
| `130` | `CANCELLED` | Execution interrupted via `SIGINT` (Ctrl+C) |

---

## Configuration & Environment Variables

| Setting Key | Environment Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `base_dir` | `NAMI_BASE_DIR` | `~/Nami/downloads` | Root directory for downloads |
| `cookies_dir` | `NAMI_COOKIES_DIR` | `~/Nami/cookies` | Directory for Netscape cookies |
| `profiles_dir` | `NAMI_PROFILES_DIR` | `~/Nami/profiles` | Directory for target profile lists |
| `browser` | `NAMI_BROWSER` | `brave` | Browser for automated cookie extraction |
| `user_agent` | `NAMI_USER_AGENT` | Chrome default | HTTP User-Agent header |
| `timeout_seconds` | `NAMI_TIMEOUT_SECONDS` | `1800` | Process execution deadline in seconds |
| — | `NAMI_THEME` | `auto` | Terminal styling theme (`dark`, `light`, `auto`) |
| — | `NAMI_SKIP_ENV_CHECK` | `0` | Set to `1` to bypass startup environment checks |

---

## Development & Verification

### Local environment setup

```bash
git clone https://github.com/OpenSelena/nami.git
cd nami
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Verification commands

```bash
# Run pytest unit test suite
python -m pytest

# Run Ruff linter and code formatter checks
python -m ruff check src tests
python -m ruff format --check src tests

# Verify package build & metadata
python -m build
python -m twine check dist/*
```

---

## License

Distributed under the [MIT License](LICENSE). Developed and maintained by **[Igect](https://github.com/Igect)** under **[OpenSelena](https://github.com/OpenSelena)**.

# Nami

Nami is an open-source Python CLI for downloading media from Instagram, TikTok, Facebook, and X. It wraps `gallery-dl` and `yt-dlp` with safer target parsing, per-media archives, retry/fallback logic, workspace configuration, diagnostics, and an optional Rich-powered interactive UI.

> Use Nami only for content you are allowed to access and download. Platform availability can change when upstream sites or extractors change.

## Highlights

- Interactive no-argument menu for guided setup and downloads.
- Noninteractive CLI for scripts, CI, and automation.
- Downloads explicit URLs or profile lists from a workspace.
- Supports photos, videos, stories, and highlights where upstream extractors support them.
- Uses per-target archives to avoid duplicate downloads without deleting archives implicitly.
- Validates target names and proves output paths stay inside the configured workspace.
- Supports Netscape cookie files and TikTok browser-cookie fallback.
- Classifies auth, cookie, rate-limit, network, dependency, not-found, extractor, timeout, and unknown failures.
- Provides JSON output for `download`, `doctor`, `setup`, `config`, and archive reset workflows.
- Includes a read-only `doctor` command for local diagnostics.

## Platform support

| Platform | Photos/posts | Videos/reels | Stories | Highlights | Authentication |
| --- | :---: | :---: | :---: | :---: | --- |
| Instagram | Yes | Yes | Yes | Yes | Optional Netscape cookies |
| TikTok | Limited by upstream extractor | Yes | No | No | Netscape cookies or configured browser cookies |
| Facebook | Limited by upstream extractor | Yes | No | No | Optional Netscape cookies |
| X / Twitter | Limited by upstream extractor | Yes | No | No | Optional Netscape cookies |

Unsupported combinations are reported as unsupported operations instead of being silently treated as successful downloads.

## Installation

```bash
python -m pip install nami
```

Upgrade an existing installation:

```bash
python -m pip install --upgrade nami
```

Nami requires Python 3.10 or newer. Runtime dependencies are installed automatically: `rich`, `gallery-dl`, and `yt-dlp`.

## Quick start

### Interactive mode

Run Nami without arguments:

```bash
nami
```

The interactive UI guides you through workspace setup, settings, profile-file downloads, and media selection. Nami no longer creates a workspace as a hidden import-time side effect; setup is explicit through the interactive prompt or the `setup` command.

### Noninteractive setup

Create a workspace under a chosen root directory:

```bash
nami setup --root .
```

This creates:

```text
Nami/
├── downloads/
├── cookies/
└── profiles/
    ├── facebook_profiles.txt
    ├── instagram_profiles.txt
    ├── tiktok_profiles.txt
    └── x_profiles.txt
```

Create optional cookie templates too:

```bash
nami setup --root . --cookie-templates
```

### Download explicit URLs

```bash
nami download https://www.instagram.com/example/ --media photos,videos
```

Multiple URLs are supported:

```bash
nami download URL1 URL2 URL3 --media all
```

Force platform inference when a URL is ambiguous:

```bash
nami download https://x.com/example --platform x --media videos
```

### Download from profile files

Add one profile URL per line in the appropriate file under `Nami/profiles/`, then run:

```bash
nami download --profiles --media photos,videos
```

Limit profile loading to one platform:

```bash
nami download --profiles --platform instagram --media stories,highlights
```

### JSON output

Use `--json` for machine-readable output:

```bash
nami download --profiles --media all --json
nami doctor --json
nami config show --json
```

## CLI reference

```text
nami setup --root PATH [--cookie-templates] [--json]
nami download [URL ...] [--profiles] [--platform instagram|tiktok|facebook|x] [--media KINDS] [--json]
nami doctor [--json]
nami config show|get|set|unset ... [--json]
nami archive reset (--all | selectors...) [--dry-run] [--yes] [--delete] [--json]
```

Media kinds are `photos`, `videos`, `stories`, `highlights`, or `all`. Comma-separated values are accepted, for example `photos,videos`.

## Configuration

Nami loads configuration in this order:

1. Environment variables
2. `~/.nami/nami_config.json`
3. Defaults based on the current user's home directory

The config file is written atomically and avoids world-readable permissions where the platform supports it.

### Config commands

```bash
nami config show
nami config get base_dir
nami config set browser firefox
nami config unset browser
```

Supported keys:

| Key | Environment variable | Description |
| --- | --- | --- |
| `base_dir` | `NAMI_BASE_DIR` | Download output directory |
| `cookies_dir` | `NAMI_COOKIES_DIR` | Netscape cookie file directory |
| `profiles_dir` | `NAMI_PROFILES_DIR` | Profile text-file directory |
| `browser` | `NAMI_BROWSER` | Browser for TikTok browser-cookie fallback (`brave`, `chrome`, `edge`, `firefox`) |
| `user_agent` | `NAMI_USER_AGENT` | User-Agent sent to extractors |
| `timeout_seconds` | `NAMI_TIMEOUT_SECONDS` or `NAMI_TIMEOUT` | Per-attempt subprocess timeout |

## Authentication and cookies

Place Netscape-format cookie files in the configured cookie directory. Nami validates that files contain at least one real seven-column Netscape cookie row; placeholder files and headers alone are rejected.

Common cookie candidate names include platform-specific files such as:

```text
instagram_cookies.txt
tiktok_cookies.txt
facebook_cookies.txt
x_cookies.txt
```

TikTok can fall back to browser cookie extraction when no valid cookie file is available. If the configured browser is running, its database may be locked; `nami doctor` reports this as a warning.

## Archives

Each target/media operation uses an archive file to avoid duplicate downloads. Archives are never deleted implicitly.

Preview archive reset actions:

```bash
nami archive reset --all --dry-run
```

Back up matching archives after confirmation:

```bash
nami archive reset --platform instagram --target example --yes
```

Permanently delete matching archives only when intentional:

```bash
nami archive reset --all --delete --yes
```

Without `--yes`, archive reset reports a dry run only.

## Diagnostics

Run local, read-only diagnostics:

```bash
nami doctor
```

Doctor checks include:

- configuration validity
- Python version
- importability of runtime dependencies
- workspace readability/writability
- configured browser state
- cookie-file validity
- profile-file readability
- potential `urllib3` namespace conflicts
- stale archive locks

Doctor does not make network requests and does not mutate the workspace.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success |
| 1 | Failure |
| 2 | Invalid input or configuration |
| 3 | Partial result, warning, or unsupported-only result |
| 4 | No results |
| 130 | Cancelled |

## Development

Clone the repository, create an environment, and install development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

Run tests and quality checks:

```bash
PYTHONPATH=src python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m build
python -m twine check dist/*
check-wheel-contents dist/*.whl
```

The test suite is designed to avoid network calls.

## Troubleshooting

- Run `nami doctor` first; it provides targeted remediation messages.
- If `pytest` imports an installed old copy of Nami, run with `PYTHONPATH=src` or install the package editable with `python -m pip install -e .[dev]`.
- If cookie authentication fails, export fresh Netscape cookies and ensure the file has real cookie rows, not just template comments.
- If TikTok browser-cookie extraction fails, close the configured browser and retry.
- If downloads repeatedly time out, increase `timeout_seconds` with `nami config set timeout_seconds 3600`.
- If you intentionally want to re-download content, use `nami archive reset` instead of deleting files manually.

## License

Nami is distributed under the MIT License. See `LICENSE`.

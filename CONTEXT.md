# Nami Domain Context

This document defines the core domain model, ubiquitous language, and system concepts for **Nami**.

---

## 1. Domain Vocabulary & Concepts

### Target
A normalized, immutable media destination parsed from user input or profile files.
- `original_url`: The raw URL string passed into the system.
- `canonical_url`: The sanitized, host-normalized HTTPS URL.
- `target_key`: Filesystem-safe identifier used for directory naming (e.g. `nasa` or `user_post_12345`).
- `platform`: Target social platform ([`Platform`](#platform)).
- `username`: Profile username or owner identifier (if applicable).
- `content_type`: Category of the resource (`profile`, `post`, `reel`, `story`, `highlight`, `video`).
- `content_id`: Content-specific identifier (e.g. status ID or shortcode).

### Platform
The supported social media networks:
- `instagram`: Instagram (`instagram.com`, `m.instagram.com`).
- `tiktok`: TikTok (`tiktok.com`, `m.tiktok.com`).
- `facebook`: Facebook (`facebook.com`, `fb.com`, `m.facebook.com`).
- `x`: X / Twitter (`x.com`, `twitter.com`).

### MediaKind
The requested media categories to extract:
- `photos`: Static image assets (JPEG, PNG, WebP, HEIC, etc.).
- `videos`: Video files and reels (MP4, WebM, MKV, MOV, etc.).
- `stories`: 24-hour ephemeral story media (Instagram).
- `highlights`: Saved story collections (Instagram).

### Outcome
Terminal status of a download attempt or aggregated operation:
- `downloaded`: New media files were successfully written to disk.
- `up_to_date`: Content was processed, but all items already existed in `archive.txt`.
- `no_results`: Extractor ran cleanly but found no downloadable media.
- `unsupported`: The requested media kind is not supported for this platform/target combination.
- `partial`: Mixed results across attempts or steps.
- `failed`: All download attempts exhausted without success.
- `cancelled`: Execution was aborted via SIGINT or user cancellation.
- `invalid`: The input target URL, syntax, or configuration is malformed.

### FailureKind
Classified taxonomy of command errors:
- `auth`: Authentication was rejected (HTTP 401, login required).
- `cookie`: Cookie file missing, malformed, or unable to be decrypted from browser.
- `rate_limit`: Throttled by platform (HTTP 429, too many requests).
- `network`: Connection reset, DNS failure, or SSL error.
- `extractor`: Upstream extractor error or unsupported route.
- `not_found`: Content or account deleted/private (HTTP 404).
- `dependency`: Missing Python module or CLI engine.
- `timeout`: Subprocess exceeded configured execution deadline.
- `locked`: Account checkpoint or filesystem archive lock contention.
- `config`: Malformed user settings or invalid directory paths.
- `unknown`: Unclassified failure.

### PlanStep
An atomic, deterministic execution unit produced by `planner.py`. Maps a `Target` and `MediaKind` to a specific destination folder, URL endpoint, and ordered list of downloader engines.

### Engine
A backend downloader adapter conforming to `Engine` Protocol:
- `gallery-dl`: Primary engine for image, album, and Instagram story/highlight extraction.
- `yt-dlp`: Primary/fallback engine for video feeds, direct video links, and TikTok.

### ArchiveLock
An atomic, inter-process file lock (`archive.lock`) protecting each destination directory's `archive.txt` deduplication index from concurrent corruption during execution.

### Settings
Immutable configuration loaded with precedence:
1. Environment variables (`NAMI_*`).
2. Configuration file (`~/.nami/nami_config.json`).
3. Defaults derived from user home directory.

---

## 2. Architectural Principles

1. **Pure Functional Core, Imperative Shell**: Planning (`planner.py`), target parsing (`targets.py`), and retry decisions (`retry.py`) are pure and side-effect free. Subprocess execution (`process.py`) and filesystem I/O (`archive.py`, `config.py`) are strictly isolated.
2. **Deterministic Exit Codes**:
   - `0`: Success (downloaded or up-to-date).
   - `1`: Unrecoverable download failure.
   - `2`: Invalid CLI arguments, configuration, or profile syntax.
   - `3`: Partial operations, unsupported requests, or doctor warnings.
   - `4`: Extractor completed with zero items found.
   - `130`: Cancelled by user.
3. **No Shell Invocations**: All subprocesses run via argument arrays with `shell=False` to eliminate shell injection vulnerabilities.
4. **Strict Path Containment**: All download directories and archive operations verify containment below `base_dir` using `safe_target_dir` to prevent path traversal.

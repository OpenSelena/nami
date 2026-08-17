# Changelog

All notable changes to Nami are documented here.

## [5.0.2] - 2026-08-17

### Added
- Created `CONTEXT.md` documenting Nami's domain models, ubiquitous glossary, and architectural principles.
- Added `docs/adr/0001-dual-engine-architecture.md` capturing the dual-engine (`gallery-dl` / `yt-dlp`) routing and fallback architecture.
- Added Matt Pocock engineering agent configuration (`AGENTS.md`, `docs/agents/issue-tracker.md`, and `docs/agents/domain.md`).

### Quality & Tooling
- Refactored engine adapters (`gallery-dl`, `yt-dlp`) to use typed `Platform` and `MediaKind` domain property access.
- Added `mypy` to development dependencies in `pyproject.toml`.
- Guarded `Console` type annotation with `TYPE_CHECKING` in CLI interactive entrypoint.
- Aligned `README.md` default timeout documentation (`1800s`) and `SECURITY.md` supported version policy (`5.x`).

## [5.0.1] - 2026-08-17

### Architecture and Refactoring

- Removed dead polymorphic token extractors and speculative enum resolvers in engine adapters and failure classifiers.
- Simplified domain model serialization to leverage standard library `dataclasses.asdict()`.
- Cleaned service and retry parameter signatures and eliminated redundant method and property wrappers.

## [5.0.0] - 2026-08-16

### Architecture

- Replaced the previous monolithic CLI implementation with modular packages for configuration, target parsing, authentication, archives, process execution, failure classification, retry policy, planning, service orchestration, diagnostics, and UI rendering.
- Added immutable domain models with deterministic JSON serialization and aggregate exit-code mapping.
- Added injectable engines, runners, retry policies, and event sinks to make behavior testable without network calls.

### Security and safety

- Added strict target parsing and safe output directory construction to prevent Windows path escapes, drive-prefix abuse, traversal, and control-character names.
- Added atomic configuration writes with secure best-effort permissions for config and credential-adjacent directories.
- Rejected placeholder cookie files by requiring at least one valid Netscape cookie row.
- Removed import-time global settings and avoided `os.chdir()` in core logic.
- Escaped or disabled Rich markup for dynamic terminal output.
- Preserved archives by default; archive reset is now explicit, confirmable, and dry-run capable.

### Reliability

- Added true wall-clock subprocess deadlines, bounded output capture, redacted command representation, and process-tree cleanup on Windows and POSIX.
- Added ordered failure classification for authentication, cookies, checkpointing/rate limits, networking, dependencies, not-found cases, extractor failures, timeouts, and unknown errors.
- Added retry behavior that preserves authentication until an auth failure is confirmed and only then attempts one anonymous fallback.
- Split Instagram feed and reels video planning into independent operations to avoid one failure hiding the other.
- Removed diagnostic re-download behavior; subprocess output is captured once and analyzed once.

### CLI and UX

- Added noninteractive commands: `setup`, `download`, `doctor`, `config`, and `archive reset`.
- Added JSON output for automation.
- Added deterministic exit codes for success, failure, invalid input/configuration, partial results, no results, and cancellation.
- Kept the no-argument interactive menu on top of the new domain APIs.

### Tests and CI

- Added a broad unit test suite covering configuration, targets, auth, archives, process handling, failure classification, engines, retry, planning, service orchestration, doctor, CLI, and UI behavior.
- Added reusable GitHub checks with Ruff, test matrix coverage on Ubuntu and Windows for Python 3.10 through 3.14, dependency checks, build verification, and smoke installation.
- Hardened PyPI release publishing with annotated tag validation, version matching, artifact reuse, smoke install, and OIDC-only publishing.
- Added Dependabot configuration for Python dependencies and GitHub Actions.

### Documentation

- Rewrote the README with current setup, CLI, configuration, authentication, archives, diagnostics, exit codes, development, and troubleshooting guidance.
- Rewrote the publishing guide for the OIDC-only release workflow.
- Added a security policy.

### Notes

- Earlier `v3.0.0` to `v3.0.1` history diverged from the current 5.0.0 architecture work. Treat 5.0.0 as a major stabilization and modernization release.

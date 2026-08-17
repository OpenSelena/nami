# ADR-0001: Dual-Engine Architecture with Extractor Fallback

## Status
Accepted

## Context
Different social media platforms employ varied rendering mechanisms, anti-bot protections, and content delivery architectures. While `gallery-dl` excels at multi-image carousel extraction, album pagination, and Instagram metadata handling (such as stories and highlights), `yt-dlp` provides superior video stream extraction, format muxing, and TikTok browser cookie integration.

Relying exclusively on a single tool resulted in fragile extractions when upstream platforms updated their APIs or frontend bundles.

## Decision
Nami adopts a dual-engine architecture coordinating `gallery-dl` and `yt-dlp` through a standardized `Engine` Protocol:

1. **Engine Assignment**:
   - **Photos / Images**: Exclusively routed to `gallery-dl`.
   - **Stories / Highlights**: Exclusively routed to `gallery-dl`.
   - **Videos / Reels**: Routed to `gallery-dl` first, with automatic fallback to `yt-dlp`.
   - **Direct Video / TikTok**: Uses `yt-dlp` or `gallery-dl` based on target compatibility.

2. **Fallback Isolation**:
   - Engine fallback is **only** triggered when the primary engine encounters `FailureKind.EXTRACTOR` (e.g. unsupported route or broken upstream extractor).
   - Transient network issues, rate limits, and authentication errors do **not** trigger engine fallback; they are handled by retry policies on the same engine.

3. **Output Standardization**:
   - Each engine adapter implements `build_command()` and `analyze_output()` to translate tool-specific output into standard `EngineAnalysis(downloaded, archived)` metrics.

## Consequences
- **Positive**: Significantly higher download success rates across video platforms without manual user intervention.
- **Positive**: Clean separation of tool-specific CLI options and output scrapers behind immutable `EngineRequest` and `CommandSpec` data boundaries.
- **Negative**: Requires maintaining dependencies on both `gallery-dl` and `yt-dlp`.

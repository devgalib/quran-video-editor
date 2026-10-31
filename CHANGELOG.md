# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-31

### Added

- FFmpeg render engine: background clips with 16 transition types, the recitation layer keyed with a
  screen blend (black backgrounds) or chroma key (green screen), text cards with fade and rise
  animation, and the original audio, at 1080p30 H.264.
- Chunked rendering that keeps memory under about 1 GB however many clips are used, joins chunks
  without re-encoding, and resumes a stopped render.
- Six card templates (royal, minimal, frame, corner, bismillah, bismillah_frame) with correct Arabic
  shaping, using the bundled Amiri, Aref Ruqaa, Cinzel and Montserrat fonts.
- Desktop app (PySide6): live preview, a picker for all 114 surahs, card editor, and render with
  progress and cancel.
- Command line: `render` (single projects and batch files), `cards`, `templates`, `scan`, `encoders`.
- MCP server (`qve mcp`) so Claude and other MCP clients can make videos.
- Optional NVIDIA, Intel and AMD hardware encoders.

[Unreleased]: https://github.com/devgalib/quran-video-editor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/devgalib/quran-video-editor/releases/tag/v0.1.0

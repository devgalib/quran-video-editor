# Contributing

Thank you for helping. Bug reports, new card templates, translations of the UI, docs fixes and
performance work are all welcome.

## Ground rules

- Be kind; this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- The Quran text in videos comes from the user's own recitation video. This project never
  generates or changes Quranic text, and contributions must keep it that way.
- Keep it light. The target machine is an 8 GB laptop without a dedicated GPU, so measure memory and
  speed for anything that touches rendering (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).
- Only add assets (fonts, images) under a licence that allows redistribution, together with that licence.

## Set up

You need Python 3.10+ and FFmpeg 6+.

```bash
git clone https://github.com/devgalib/quran-video-editor.git
cd quran-video-editor
python -m venv .venv
.venv/bin/pip install -e ".[all,dev]"     # Windows: .venv\Scripts\pip install -e ".[all,dev]"
```

Run the app with `.venv/bin/qve gui`, or the command line with `.venv/bin/qve --help`.

## Before you open a pull request

```bash
ruff check .            # lint
python -m pytest        # tests (they make tiny synthetic videos, so FFmpeg must be installed)
```

CI runs the same checks on Linux, Windows and macOS.

- One topic per pull request, with a clear description of what changed and why.
- Add or update tests for behaviour changes. Rendering changes should keep `tests/test_render.py` passing.
- If the change is visible (a card template, the window), add a screenshot to the pull request.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).

## Adding a card template

1. Write a function in [qve/cards/templates.py](qve/cards/templates.py) that draws on the canvas
   (look at `royal` or `corner`), and give it a one-line docstring; that line is shown in the app.
2. Register it in `TEMPLATES`, and add a friendly name in `TEMPLATE_NAMES` in
   [qve/gui/window.py](qve/gui/window.py).
3. Run `qve cards your-project.json` to check it at full size, and test it with long and missing fields.

## Releases (maintainers)

1. Move the **Unreleased** notes in `CHANGELOG.md` under a new version heading.
2. Bump `__version__` in `qve/__init__.py`.
3. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The Release workflow builds the
   Windows, Linux and macOS apps and publishes the GitHub release.

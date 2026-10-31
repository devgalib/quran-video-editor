Quran Video Editor
==================

Start:  Windows  - double-click QuranVideoEditor.exe
        Linux    - run ./QuranVideoEditor
        macOS    - open QuranVideoEditor.app (first time: right-click > Open)

FFmpeg is needed and is not included. Install it once:
        Windows  - winget install Gyan.FFmpeg     (or put ffmpeg.exe and ffprobe.exe in a "bin" folder
                   inside the "_internal" folder of this app)
        Linux    - sudo apt install ffmpeg   /   sudo dnf install ffmpeg
        macOS    - brew install ffmpeg

The same program also works from a terminal:
        QuranVideoEditor render project.json
        QuranVideoEditor --help

Documentation, source code and issues: https://github.com/devgalib/quran-video-editor
License: MIT (see LICENSE). Fonts: SIL Open Font License (see font-licenses).

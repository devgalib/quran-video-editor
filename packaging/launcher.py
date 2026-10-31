"""Entry point for the packaged desktop app (PyInstaller): no arguments opens the window,
any arguments run the command line, e.g. `QuranVideoEditor render project.json`."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from qve.cli import main
    else:
        from qve.gui import main
    sys.exit(main())

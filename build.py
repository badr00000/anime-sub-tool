"""Build AnimeSubTool.exe — one self-contained file (Python, Qt, mkvmerge all inside).

Usage:  py -3.11 build.py
Output: dist/AnimeSubTool.exe
"""

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).parent.absolute()


def build():
    print("Building Anime Subtitle Automation Tool (single file)...")

    args = [
        str(ROOT / "main.py"),
        "--name=AnimeSubTool",
        "--onefile",            # everything packed into one .exe
        "--windowed",           # no console window behind the GUI
        f"--icon={ROOT / 'app_icon.ico'}",
        "--noconfirm",
        "--clean",
        f"--distpath={ROOT / 'dist'}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
        # Source packages are also shipped as data so path-based lookups
        # (bin/mkvmerge.exe, gui/assets/*.svg) work inside the bundle.
        f"--add-data={ROOT / 'gui'};gui",
        f"--add-data={ROOT / 'core'};core",
        f"--add-data={ROOT / 'cli'};cli",
        f"--add-data={ROOT / 'utils'};utils",
        # Only mkvmerge is needed at run time (not the whole bin folder)
        f"--add-data={ROOT / 'bin' / 'mkvmerge.exe'};bin",
        f"--add-data={ROOT / 'app_icon.ico'};.",
        # Licence notices, shown by About -> Licenses
        f"--add-data={ROOT / 'THIRD_PARTY_LICENSES.md'};.",
        f"--add-data={ROOT / 'licenses'};licenses",
    ]

    try:
        PyInstaller.__main__.run(args)
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)
    print(f"\nBuild complete: {ROOT / 'dist' / 'AnimeSubTool.exe'}")


if __name__ == "__main__":
    build()

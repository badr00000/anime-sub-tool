# Third-party software

Anime Subtitle Automation Tool uses and redistributes the software listed below.
Each component remains under its own licence. The downloadable `AnimeSubTool.exe`
contains all of them; this file is shipped inside it and shown by
**About -> Licenses**.

## MKVToolNix (mkvmerge) v100.0 — GNU General Public License, version 2

- Program: `mkvmerge.exe`, bundled unmodified in `bin/` and run as a separate program.
- Exact version: MKVToolNix 100.0 ('Do Hot Girls Like Chords'), 64-bit Windows
  build, as published by the MKVToolNix project (`mkvmerge --version` prints
  `mkvmerge v100.0 ('Do Hot Girls Like Chords') 64-bit`).
- Copyright (C) Moritz Bunkus and the MKVToolNix contributors.
- Home page and official binaries: https://mkvtoolnix.download/
- Complete corresponding source code of this exact version: the MKVToolNix
  release page for 100.0, https://mkvtoolnix.download/source.html (archive
  `mkvtoolnix-100.0.tar.xz`), and the tag `release-100.0` of
  https://codeberg.org/mbunkus/mkvtoolnix
- Written offer: for at least three years after the last time this application
  is distributed, its author will give anyone who asks a complete copy of the
  corresponding source code of the bundled mkvmerge (MKVToolNix 100.0), on a
  medium customarily used for software interchange, for no more than the cost of
  physically providing it. Ask through the project's issue tracker or the
  contact given where you obtained the application.
- Licence: GNU GPL version 2. The full text is in `licenses/GPL-2.0.txt`
  and follows this list in the About -> Licenses window.

mkvmerge itself includes other libraries (libEBML, libMatroska, Boost, zlib and
more); their notices are part of the MKVToolNix source distribution above.

## Qt 6 and PySide6 (Qt for Python) — GNU Lesser General Public License, version 3

- Copyright (C) The Qt Company Ltd. and other contributors.
- Used as dynamically loaded libraries, unmodified.
- Home pages: https://www.qt.io/ and https://doc.qt.io/qtforpython-6/
- Source code: https://code.qt.io/ and https://download.qt.io/official_releases/QtForPython/
- Licence text (LGPLv3): https://www.gnu.org/licenses/lgpl-3.0.html
  Licensing overview: https://doc.qt.io/qtforpython-6/licenses.html
- You may replace the Qt / PySide6 libraries with your own build: run the
  application from its source code (`py -3.11 main.py`) with the PySide6 version
  of your choice, or rebuild the executable with `build.py`.
- Qt itself contains third-party code (for the multimedia module this includes
  FFmpeg, used under the LGPL); see https://doc.qt.io/qt-6/licenses-used-in-qt.html

## anitopy — Mozilla Public License 2.0

- Anime file name parser. Copyright (C) its authors.
- Source: https://github.com/igorcmoura/anitopy
- Licence text: https://www.mozilla.org/MPL/2.0/

## RapidFuzz — MIT License

- Fuzzy string matching. Copyright (C) Max Bachmann.
- Source: https://github.com/rapidfuzz/RapidFuzz
- Licence text: https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE

## click — BSD 3-Clause License

- Command line interface toolkit. Copyright (C) Pallets.
- Source: https://github.com/pallets/click
- Licence text: https://github.com/pallets/click/blob/main/LICENSE.txt

## watchdog — Apache License 2.0

- File system monitoring. Copyright (C) Yesudeep Mangalapilly, Google Inc. and contributors.
- Source: https://github.com/gorakhargosh/watchdog
- Licence text: https://www.apache.org/licenses/LICENSE-2.0

## Python and PyInstaller (executable only)

- The executable embeds the CPython interpreter and standard library
  (Python Software Foundation License, https://docs.python.org/3/license.html).
- It is packaged with PyInstaller, whose bootloader is distributed under the GPL
  with an exception that allows bundling any program
  (https://pyinstaller.org/en/stable/license.html).

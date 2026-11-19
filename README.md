# Anime Subtitle Automation Tool v2.0

A Windows desktop tool that merges a season of anime episodes with their
downloaded subtitle files in one go. It pairs each episode with its subtitle by
episode number, runs `mkvmerge` for every pair, and writes the results to a
separate folder. **The original files are never modified.**

It also includes a small standalone tool to fix subtitle timing (Sync Subtitle).

## Features

- **Merge Season** — a four-step wizard: *Select* a folder, *Preview* the
  pairing, *Process*, *Results*.
- **Matching by episode number.** File names are parsed with `anitopy`
  (plus fallback patterns), so `[Cleo]Mousou_Dairinin_-_01` is paired with
  `[Scarlet Team] Paranoia Agent - 01`. What the matcher does and does not do:
  - the episode number decides the pairing; when both names state a season
    (`S02E05`, `2nd Season`) the seasons must agree too;
  - the title similarity (via `rapidfuzz`) is shown as a percentage. Different
    titles do **not** block a match — groups use different spellings and
    translated titles — but such rows are flagged `⚠ CHECK` in the preview so
    you can verify them;
  - openings, endings, previews, menus and similar extras (`NCOP`, `NCED`, `OP`,
    `ED`, `PV`, `Preview`, `Menu`, …) are never paired with an episode subtitle;
    `OVA` / `Special` files are only paired with a subtitle that is also marked
    `OVA` / `Special`;
  - a multi-episode file such as `01-02` is matched by its first number;
  - if `Show - 01.srt` and `Show - 01.synced.srt` both exist, the synced copy is used;
  - when several files compete for the same subtitle, the best-matching pair wins
    whatever the file order: `5 Centimeters per Second (2007).mkv` (read as
    episode 5) does not take `Show - 05.srt` away from `Show - 05.mkv`;
  - **films and other files without an episode number** pair on their name, with
    bracket tags, release tags (`1080p`, `BluRay`, `x265`, …), years, a trailing
    scene group (`-GROUP`) and the subtitle's language code ignored:
    `Suzume.2022.1080p.BluRay.x265-GROUP.mkv` pairs with `Suzume.ar.srt` or
    `Suzume.2022.ar.srt`. A title that is only a year (`1917`) is kept. Language
    codes are only removed from subtitle names (`Tenki.no.Ko.mkv` keeps its `Ko`);
  - **language tags**: a subtitle name may say its language — a suffix such as
    `.ar`, `.ara`, `.en`, `.eng`, `.ja` (any code, alias or name the language
    dropdowns know) or a bracket such as `(English)`, `[ENG]`, `(عربي)`, `[Arabic]`.
    A subtitle in the language you chose for the new track (Subtitle *Language*
    option, default from Settings) wins, then one without a tag; one tagged with
    another language never beats those. If it is the only candidate it is still
    paired, but the row is flagged `⚠ CHECK` ("subtitle looks like English, track
    will be labelled Arabic"). The detected tag is shown in the subtitle's tooltip.
- **Track cleanup** — keep only the audio languages you choose, remove (or
  keep) the subtitles already inside the episode, optionally relabel an
  existing subtitle track.
- **Subtitle options** — language and track name, timing shift, and character
  encoding. Encoding is auto-detected (UTF-8, UTF-16, Windows-1256 Arabic,
  Windows-1252 Western, Shift-JIS, GB18030, Big5, EUC-KR) or can be chosen by
  hand; legacy encodings are converted to UTF-8 inside the MKV. The detected
  encoding is shown in the tooltip of each subtitle in the preview.
- **Language dropdowns everywhere** — pick `Japanese (jpn)` from a searchable
  list instead of typing codes. The search accepts English names, ISO codes and
  Arabic names (for example `ياباني`).
- **Presets** — save the options panel under a name and load it later.
- **Watch folder** — optional: while it is ticked on the first page, the folder
  is **rescanned automatically** when video or subtitle files are added or
  changed. It only refreshes the scan; processing always starts with your click.
- **Sync Subtitle** — play an episode with a `.srt` / `.ass` / `.ssa` subtitle
  drawn on top, nudge the subtitle earlier or later while watching (`G` / `H`,
  like VLC), then save a shifted copy as `name.synced.srt`. A warning appears
  when a negative shift would push lines before 0:00. The loaded subtitle is
  only overwritten after an explicit confirmation.
- **Portable** — `mkvmerge` (MKVToolNix v100.0) is bundled; nothing else has to
  be installed to use the `.exe`.

## How to use (Merge Season)

1. **Select** — drop or browse to the folder that contains the episodes
   (`.mkv`, `.mp4`, `.avi`, …) and the subtitle files (`.srt`, `.ass`, `.ssa`,
   `.vtt`, VobSub `.idx`+`.sub`). Click **SCAN FOLDER**.
2. **Preview** — the table lists every episode, the subtitle it was paired
   with, the title similarity and a status (`READY`, `⚠ CHECK`, `NO SUB`).
   Adjust the options on the right if needed.
   **Fix a pairing by hand:** double-click a SUBTITLE FILE cell (or select the
   row and press Enter, Space or F2) and pick any subtitle of the folder, or
   `— none —`. The row then shows `MANUAL`, and the counters update. A subtitle
   can belong to one episode only: picking one that another episode had moves it
   (that episode is left without a subtitle). Processing uses the pairs as shown.
   Choices made by hand are kept when you change the subtitle language, but a
   rescan of the folder (including an automatic one from *Watch folder*) resets them.
3. Click **START PROCESSING**. Up to 8 episodes are processed at once
   (default 4; change it with *Episodes at once*). **CANCEL** lets running
   episodes finish and skips the rest.
4. **Results** — counts of done / skipped / failed / cancelled episodes, with
   the reasons. **OPEN OUTPUT FOLDER** opens the folder the files were written to.

Good to know:

- Output goes to a `PROCESSED/` subfolder of the season folder (the name can be
  changed in Settings). Output files are always `.mkv`.
- If *Save into a PROCESSED/ subfolder* is unticked, the new files are written
  next to the episodes as `name [AnimeSubTool].mkv`; files with that marker are
  ignored by later scans.
- An output file that already exists is **skipped** unless *Overwrite existing
  output files* is ticked.
- Episodes without a matching subtitle are **skipped** unless *Also process
  episodes that have no subtitle* is ticked.
- *Dry run* simulates the batch and writes nothing.
- A subtitle file with no subtitle lines is reported as a failure for that episode.

Settings (sidebar) holds the defaults: subtitle language and name, episodes at
once, output subfolder name, and an optional MKVToolNix folder. Leave the
MKVToolNix folder empty to use the bundled copy.

Settings and logs are stored in `%USERPROFILE%\.anime-sub-tool\`.

## Run from source

Requirements: Windows, Python 3.11.

```bash
git clone https://github.com/<your-username>/anime-sub-tool.git   # <your-username> is a placeholder
cd anime-sub-tool
py -3.11 -m pip install -r requirements.txt
py -3.11 main.py
```

### Command line (from source only)

The CLI is available when running from source: `py -3.11 main.py <command>`.
It is **not** available from `AnimeSubTool.exe`, which is a windowed program
without a console.

```bash
py -3.11 main.py scan "D:\Anime\Show"                 # show the pairing
py -3.11 main.py preview "D:\Anime\Show"              # show what process would do
py -3.11 main.py process "D:\Anime\Show" --yes        # merge the season
py -3.11 main.py shift "Show - 01.srt" --offset 1.5   # write Show - 01.synced.srt
py -3.11 main.py --help
```

`process` options: `--workers N` (1-8), `--output DIR`, `--dry-run`, `--yes`,
`--offset SECONDS`, `--sub-charset NAME`, `--keep-audio LANGS`, `--keep-subs LANGS`,
`--keep-original-subs`, `--overwrite`, `--include-unmatched`.
`--offset` accepts -3600 to 3600 seconds (the same ±1 hour limit as the GUI).

By default `process` keeps only Japanese audio (every audio track when an episode
has no Japanese one) and removes every subtitle already in the episode.
`--keep-audio jpn,eng` keeps those audio languages, `--keep-audio all` keeps all
audio; `--keep-subs eng` keeps the original English subtitles while removing the
rest, and `--keep-subs all` keeps every original subtitle (the same as
`--keep-original-subs`). Any spelling works (`ja`, `jpn`, `ja-JP`). When the new subtitle is set as
default, kept original subtitles lose their default flag. Defaults (language, track name, workers, subfolder,
MKVToolNix folder) come from the same settings file the GUI uses.

`shift` refuses to write over the file it read unless `--force` is given.

### Tests

```bash
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest -q
```

### Build the portable EXE

```bash
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 build.py
```

The result is one file, `dist/AnimeSubTool.exe`, containing Python, Qt and
`mkvmerge`. Copy it anywhere and double-click it. The first launch takes a few
seconds because the bundle unpacks itself to a temporary folder.

## License

This project's own code is released under the [MIT License](LICENSE).
The bundled third-party programs and libraries keep their own licences (below).

## Third-party software and licenses

This tool bundles and uses third-party software, each under its own licence:
MKVToolNix / mkvmerge (GPLv2), Qt and PySide6 (LGPLv3), anitopy (MPL-2.0),
RapidFuzz (MIT), click (BSD-3-Clause) and watchdog (Apache-2.0).

See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for the notices and source
code locations, and [licenses/GPL-2.0.txt](licenses/GPL-2.0.txt) for the full
GPLv2 text. The same information is available inside the app under
**About -> Licenses**.

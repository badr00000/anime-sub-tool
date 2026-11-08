"""
Anime Subtitle Automation Tool — subtitle file timing (SRT / ASS / SSA)

Load a subtitle file, read its cues for on-screen preview, and write a copy with
every timestamp shifted. Only the timestamps change: text, styles, comments and
line endings are kept exactly as they were.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.subtitles import detect_charset

SUPPORTED_EXTENSIONS = {".srt", ".ass", ".ssa"}

# 00:01:23,450 --> 00:01:26,100   (also accepts '.' as the millisecond separator)
_SRT_TIMING = re.compile(
    r"(?P<a>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})(?P<mid>\s*-->\s*)(?P<b>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
_ASS_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})[.,](\d{1,3})$")
_ASS_OVERRIDE = re.compile(r"\{[^}]*\}")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


@dataclass
class Cue:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class SubtitleFile:
    path: Path
    kind: str                     # "srt" or "ass"
    text: str                     # full decoded content, original line endings
    encoding: str                 # encoding it was read with
    cues: list[Cue] = field(default_factory=list)


# ── time helpers ──────────────────────────────────────────────────────────────

def _srt_to_ms(value: str) -> int:
    hms, frac = re.split(r"[,.]", value)
    h, m, s = (int(x) for x in hms.split(":"))
    ms = int(frac.ljust(3, "0")[:3])
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def _ms_to_srt(ms: int) -> str:
    ms = max(0, int(round(ms)))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_to_ms(value: str) -> Optional[int]:
    match = _ASS_TIME.match(value.strip())
    if not match:
        return None
    h, m, s, frac = match.groups()
    # ASS uses centiseconds ("0:01:23.45"); be lenient with 1-3 digits
    ms = int(frac.ljust(3, "0")[:3]) if len(frac) != 2 else int(frac) * 10
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + ms


def _ms_to_ass(ms: int) -> str:
    cs = max(0, int(round(ms / 10)))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def format_offset(ms: int) -> str:
    """'+1.250 s' / '-0.050 s' — how the UI and logs show an offset."""
    sign = "+" if ms >= 0 else "−"
    return f"{sign}{abs(ms) / 1000:.3f} s"


# ── loading ───────────────────────────────────────────────────────────────────

def _read_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    charset = detect_charset(path) or "utf-8"
    return data.decode(charset, errors="replace"), charset


def _clean_srt_text(text: str) -> str:
    return _HTML_TAG.sub("", text).strip()


def _clean_ass_text(text: str) -> str:
    text = _ASS_OVERRIDE.sub("", text)
    return text.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ").strip()


def _ass_event_columns(lines: list[str]) -> tuple[int, int, int, int]:
    """Indexes of Start, End and Text in [Events] 'Format:', plus the field count."""
    in_events = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_events = stripped.lower() == "[events]"
            continue
        if in_events and stripped.lower().startswith("format:"):
            cols = [c.strip().lower() for c in stripped.split(":", 1)[1].split(",")]
            if "start" in cols and "end" in cols and "text" in cols:
                return cols.index("start"), cols.index("end"), cols.index("text"), len(cols)
    # Standard v4+ layout: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    return 1, 2, 9, 10


def load(path: str | Path) -> SubtitleFile:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported subtitle type '{ext}'. Use .srt, .ass or .ssa.")
    text, encoding = _read_text(path)

    if ext == ".srt":
        sub = SubtitleFile(path, "srt", text, encoding)
        blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
        for block in blocks:
            lines = block.splitlines()
            for i, line in enumerate(lines):
                m = _SRT_TIMING.search(line)
                if m:
                    sub.cues.append(Cue(_srt_to_ms(m["a"]), _srt_to_ms(m["b"]),
                                        _clean_srt_text("\n".join(lines[i + 1:]))))
                    break
        return sub

    sub = SubtitleFile(path, "ass", text, encoding)
    lines = text.splitlines()
    start_i, end_i, text_i, n = _ass_event_columns(lines)
    for line in lines:
        if not line.lstrip().lower().startswith("dialogue:"):
            continue
        fields = line.split(":", 1)[1].split(",", n - 1)
        if len(fields) < n:
            continue
        a, b = _ass_to_ms(fields[start_i]), _ass_to_ms(fields[end_i])
        if a is None or b is None:
            continue
        sub.cues.append(Cue(a, b, _clean_ass_text(fields[text_i])))
    sub.cues.sort(key=lambda c: c.start_ms)
    return sub


# ── shifting ──────────────────────────────────────────────────────────────────

def shifted_text(sub: SubtitleFile, offset_ms: int) -> str:
    """Return the file content with every timestamp moved by offset_ms (clamped at 0)."""
    if offset_ms == 0:
        return sub.text

    if sub.kind == "srt":
        def repl(m: re.Match) -> str:
            return (_ms_to_srt(_srt_to_ms(m["a"]) + offset_ms) + m["mid"]
                    + _ms_to_srt(_srt_to_ms(m["b"]) + offset_ms))
        return _SRT_TIMING.sub(repl, sub.text)

    lines = sub.text.splitlines(keepends=True)
    start_i, end_i, _, n = _ass_event_columns([l.rstrip("\r\n") for l in lines])
    out = []
    for line in lines:
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        stripped = body.lstrip()
        if stripped.lower().startswith(("dialogue:", "comment:")):
            prefix, rest = body.split(":", 1)
            fields = rest.split(",", n - 1)
            if len(fields) >= n:
                for idx in (start_i, end_i):
                    ms = _ass_to_ms(fields[idx])
                    if ms is not None:
                        lead = fields[idx][: len(fields[idx]) - len(fields[idx].lstrip())]
                        fields[idx] = lead + _ms_to_ass(ms + offset_ms)
                body = prefix + ":" + ",".join(fields)
        out.append(body + ending)
    return "".join(out)


def default_output_path(path: str | Path) -> Path:
    """'Show - 01.srt' -> 'Show - 01.synced.srt' (never the original file)."""
    path = Path(path)
    stem = path.stem[:-7] if path.stem.endswith(".synced") else path.stem
    return path.with_name(f"{stem}.synced{path.suffix}")


def save_shifted(sub: SubtitleFile, offset_ms: int, output: str | Path | None = None) -> Path:
    """Write a shifted copy as UTF-8 with BOM (players detect Arabic reliably).

    Default target is 'name.synced.ext' next to the source, so the original is never
    touched; re-syncing a '.synced' file updates that same copy.
    """
    out = Path(output) if output else default_output_path(sub.path)
    content = shifted_text(sub, offset_ms)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        f.write(content)
    return out

import re
from pathlib import Path
from typing import Iterable, Optional

try:
    import anitopy
    HAS_ANITOPY = True
except ImportError:
    HAS_ANITOPY = False

from rapidfuzz import fuzz
from core.languages import NAMES as _LANGUAGE_NAMES, normalize as _normalize_language
from core.models import EpisodeInfo, EpisodeMatch, MatchConfidence
from core.constants import EPISODE_PATTERNS, OUTPUT_MARKER, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from utils.logger import get_logger
from utils.paths import is_tool_output

logger = get_logger(__name__)

# Numbers in a filename that are never the episode number: resolutions
# (1080p, 1920x1080), codecs (x264, h.265), bit depth (10bit), years, CRC hashes.
_NON_EPISODE_NUMBERS = re.compile(
    r'\d{3,4}\s*[pi]\b'
    r'|\d{3,4}\s*x\s*\d{3,4}'
    r'|[xh]\.?26[45]'
    r'|\d+\s*-?\s*bits?\b'
    r'|\b(?:19|20)\d{2}\b'
    r'|\b[0-9a-f]{8}\b',
    re.IGNORECASE,
)


# Kinds of extras. Each pairs only with a subtitle of the same kind and number:
# 'Show - NCOP1.mkv' never receives the subtitle of episode 1, 'Show OVA - 01'
# only takes a subtitle that is also marked OVA.
_KIND_ALIASES = {
    "OPENING": "OP", "ENDING": "ED", "OAD": "OVA", "OAV": "OVA", "SP": "SPECIAL",
    "SPECIALS": "SPECIAL", "CREDITLESS": "NCOP", "CREDITLESSOP": "NCOP",
    "CREDITLESSED": "NCED",
}
# Short markers count only in capitals ('Ed Edd n Eddy' is a title, 'ED2' is not)
_EXTRA_KEYWORD = (
    r'(?<![A-Za-z])(?:'
    r'(?i:NC[ ._-]?OP|NC[ ._-]?ED|Creditless(?:[ ._-]?(?:OP|ED))?|Opening|Ending|Preview'
    r'|Menu|Trailer|Specials?|OVA|OAD|OAV)'
    r'|OP|ED|PV|CM|SP)(?![A-Za-z])'
)
_KEYWORD = re.compile(_EXTRA_KEYWORD)
# Separate runs are numbered 'Show OVA - 01'; for the others ('Happy Ending - 01',
# 'Opening Night - 01') only a number glued to the word counts ('OP1', 'OP 01').
# Marker numbers have 1-3 digits: 'ED921796' is a CRC, not ending 921796.
_SEPARATE_RUN_NUMBER = re.compile(r'[ ._]*-?[ ._]*\d{1,3}(?!\d)')
_ATTACHED_NUMBER = re.compile(r'[ ._-]?\d{1,3}(?!\d)')
_AFTER_EPISODE_DASH = re.compile(r'\s-\s*$')
# A marker right after the episode number: 'Show - 01 OP', 'Show - 01 - Preview',
# 'Show_05_ED', 'Show S01E05 OP'. It must end the name ('Show 2 Opening Night - 01'
# is a title).
_AFTER_EPISODE_NUMBER = re.compile(r'(?:^|[\s._-]|(?<=\d)[Ee])\d{1,4}(?:v\d)?[ ._]*(?:-[ ._]*)?$')
_NOTHING_AFTER = re.compile(r'[\s._-]*(?:\d{1,3})?[\s._-]*')
# A bracket holding nothing but a marker: '[OP]', '(NCED 2)', '[Creditless OP]'
_BRACKET = re.compile(r'[\[(]([^\[\]()]*)[\])]')
_MARKER_ONLY = re.compile(r'^\s*(?:' + _EXTRA_KEYWORD + r')(?:[ ._-]?\d{1,3})?'
                          r'(?:\s+(?:' + _EXTRA_KEYWORD + r'))?\s*$')
_CRC = re.compile(r'\s*[0-9A-Fa-f]{8}\s*')
_VERSION = re.compile(r'(?<=\d)v(\d{1,2})(?![A-Za-z0-9])', re.IGNORECASE)

_SEASON_PATTERNS = (
    re.compile(r'(?<![A-Za-z0-9])S(\d{1,2})E\d{1,4}', re.IGNORECASE),
    re.compile(r'(?<![A-Za-z])Season[ ._-]?(\d{1,2})(?!\d)', re.IGNORECASE),
)
_SYNCED_SUFFIX = ".synced"


def normalize_episode_num(value) -> Optional[str]:
    """Return a canonical episode number so '01', '1' and '001' compare equal.

    A multi-episode file ('01-02', which anitopy returns as a list) is matched
    by its FIRST number only: one output file can take one subtitle file.
    Non-integer values such as '12.5' are kept as-is.
    """
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return str(int(text))
    try:
        return format(float(text), "g")
    except ValueError:
        return text


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _kind_name(word: str) -> str:
    key = re.sub(r'[ ._-]', '', word.upper())
    return _KIND_ALIASES.get(key, key)


def _extra_kind(stem: str) -> str:
    """'' for a normal episode, else the normalised kind of extra.

    A marker word only counts next to a number ('NCOP1', 'OP 01', 'OVA - 02'),
    right after the episode dash ('Show - OP'), or alone in a bracket that is not
    the leading group tag ('- 05 [Creditless OP]'). The same words inside a
    title ('Happy Ending - 01', 'Special A - 03', '[Specials] Show - 01') do not.
    """
    leading = len(stem) - len(stem.lstrip())
    for bracket in _BRACKET.finditer(stem):
        if bracket.start() == leading:
            continue        # '[Group]' / '[Specials]' release tag
        if _CRC.fullmatch(bracket.group(1)):
            continue        # '[ED921796]' is a CRC32 checksum
        if _MARKER_ONLY.match(bracket.group(1)):
            words = _KEYWORD.findall(bracket.group(1))
            return _kind_name(" ".join(words) if len(words) > 1 else words[0])
    # Outside brackets
    plain = _BRACKET.sub(lambda m: " " * len(m.group(0)), stem)
    for match in _KEYWORD.finditer(plain):
        kind = _kind_name(match.group(0))
        after, before = plain[match.end():], plain[:match.start()]
        number = _SEPARATE_RUN_NUMBER if kind in ("OVA", "SPECIAL") else _ATTACHED_NUMBER
        if number.match(after) or _AFTER_EPISODE_DASH.search(before):
            return kind
        if _AFTER_EPISODE_NUMBER.search(before) and _NOTHING_AFTER.fullmatch(after):
            return kind
    return ""


def _has_marker_word(stem: str) -> bool:
    """True when a marker word appears anywhere outside the leading group tag,
    even where _extra_kind() does not count it as an extra."""
    rest = stem.lstrip()
    first = _BRACKET.match(rest)
    if first:
        rest = rest[first.end():]
    return bool(_KEYWORD.search(rest))


def _parse_season(filename: str, anime_season) -> Optional[int]:
    value = _first(anime_season)
    if value is not None and str(value).strip().isdigit():
        return int(str(value).strip())
    for pattern in _SEASON_PATTERNS:
        match = pattern.search(filename)
        if match:
            return int(match.group(1))
    return None


def is_synced_copy(path: Path) -> bool:
    """True for 'name.synced.srt', the copy the Sync tool writes."""
    return Path(path).stem.lower().endswith(_SYNCED_SUFFIX)


def extract_episode_info(filepath: Path) -> EpisodeInfo:
    """Parse filename using anitopy first, then regex fallback patterns."""
    filename = filepath.name
    # 'Show - 01.synced.srt' is parsed as 'Show - 01.srt': the marker is not part of the name
    parse_name = filename
    if is_synced_copy(filepath):
        parse_name = filepath.stem[:-len(_SYNCED_SUFFIX)] + filepath.suffix
    parse_stem = Path(parse_name).stem

    episode_num = None
    series_title = None
    season = None

    if HAS_ANITOPY:
        # anitopy's anime_type is not used: it calls 'Happy Ending' an ending
        parsed = anitopy.parse(parse_name) or {}
        episode_num = normalize_episode_num(parsed.get("episode_number"))
        series_title = parsed.get("anime_title")
        season = parsed.get("anime_season")

    season = _parse_season(parse_name, season)
    extra_kind = _extra_kind(parse_stem)
    version_match = _VERSION.search(re.sub(r'\[.*?\]|\(.*?\)', ' ', parse_stem))
    version = int(version_match.group(1)) if version_match else 1

    # Fallback to regex patterns if anitopy failed or is not installed
    if not episode_num:
        for pattern in EPISODE_PATTERNS:
            match = re.search(pattern, parse_name, re.IGNORECASE)
            if match:
                episode_num = normalize_episode_num(match.group(1))
                break

    if not episode_num:
        # Final fallback: any standalone number, after removing bracketed tags,
        # the extension and numbers that are clearly not episodes (1080p, x264, 2004...).
        cleaned = re.sub(r'\[.*?\]|\(.*?\)', ' ', parse_stem)
        cleaned = _NON_EPISODE_NUMBERS.sub(' ', cleaned)
        match = re.search(r'(?<!\d)(\d{1,4})(?!\d)', cleaned)
        if match:
            episode_num = normalize_episode_num(match.group(1))

    # Try to clean up series title if missing
    if not series_title:
        # Basic heuristic: text before episode number or first bracket
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', parse_stem)
        match = re.match(r'^(.*?)(?:-\s*\d|\s+\d|_+\d)', clean_name)
        if match:
            series_title = match.group(1).strip()
        else:
            series_title = clean_name.strip()

    return EpisodeInfo(
        filepath=filepath,
        filename=filename,
        episode_num=episode_num,
        series_title=series_title,
        season=season,
        extra_kind=extra_kind,
        version=version,
    )


def list_media_files(folder_path: Path) -> tuple[list[Path], list[Path]]:
    """The episode and subtitle files directly inside a folder, sorted by name.

    Files this tool wrote itself (output marker in the name) are left out, and a
    VobSub pair (.idx + .sub) counts as one subtitle, represented by its .idx.
    """
    videos: list[Path] = []
    subtitles: list[Path] = []
    try:
        files = sorted((f for f in Path(folder_path).iterdir() if f.is_file()),
                       key=lambda f: f.name.lower())
    except OSError as e:
        logger.error(f"Could not list {folder_path}: {e}")
        return videos, subtitles

    by_ext: dict[str, set[str]] = {}
    for f in files:
        by_ext.setdefault(f.suffix.lower(), set()).add(f.stem.lower())

    for f in files:
        ext = f.suffix.lower()
        # Unfinished or temporary files of a run ('x.mkv.partial', 'x.mkv.partial.srt')
        # and finished outputs are never inputs, whatever their extension.
        if ".partial" in f.name.lower() or is_tool_output(f) or OUTPUT_MARKER in f.name:
            continue
        if ext in VIDEO_EXTENSIONS:
            videos.append(f)
        elif ext in SUBTITLE_EXTENSIONS:
            if ext == ".sub" and f.stem.lower() in by_ext.get(".idx", ()):
                continue  # the .idx stands for the pair
            if ext == ".idx" and f.stem.lower() not in by_ext.get(".sub", ()):
                continue  # an index without its .sub cannot be merged
            subtitles.append(f)
    return videos, subtitles


def scan_folder(folder_path: Path) -> tuple[list[EpisodeInfo], list[EpisodeInfo]]:
    """Scan folder for video and subtitle files.

    The folder is made absolute here, so every path handed on to mkvmerge is
    absolute whatever the caller (GUI or CLI) passed in.
    """
    folder_path = Path(folder_path).resolve()
    if not folder_path.is_dir():
        logger.error(f"Invalid directory: {folder_path}")
        return [], []

    videos, subtitles = list_media_files(folder_path)
    return ([extract_episode_info(v) for v in videos],
            [extract_episode_info(s) for s in subtitles])


def _normalize_title(title: Optional[str]) -> str:
    return " ".join(re.sub(r'[\W_]+', ' ', (title or "").lower()).split())


def _comparable_stem(info: EpisodeInfo) -> str:
    stem = info.filepath.stem
    if is_synced_copy(info.filepath):
        stem = stem[:-len(_SYNCED_SUFFIX)]
    return stem.lower()


def title_similarity(video: EpisodeInfo, subtitle: EpisodeInfo) -> float:
    """0-100: how alike the two series titles are."""
    a, b = _normalize_title(video.series_title), _normalize_title(subtitle.series_title)
    if not a or not b:
        a = _normalize_title(re.sub(r'\d+', ' ', _comparable_stem(video)))
        b = _normalize_title(re.sub(r'\d+', ' ', _comparable_stem(subtitle)))
    if a == b:
        return 100.0
    return float(fuzz.token_sort_ratio(a, b))


def _confidence(video: EpisodeInfo, subtitle: EpisodeInfo, score: float) -> MatchConfidence:
    if _comparable_stem(video) == _comparable_stem(subtitle):
        return MatchConfidence.EXACT
    if score >= 80:
        return MatchConfidence.HIGH
    if score >= 50:
        return MatchConfidence.MEDIUM
    return MatchConfidence.LOW


# Release tags that say nothing about which film or episode a file is
_RELEASE_TAGS = re.compile(
    r'(?<![a-z0-9])(?:\d{3,4}[pi]|\d{3,4}x\d{3,4}|[xh] ?26[45]|hevc|avc|av1|xvid|divx'
    r'|10 ?bits?|8 ?bits?|hdr|sdr|bd|bdrip|bdremux|bluray|blu ray|remux|dvd|dvdrip|web|web ?dl'
    r'|webrip|hdtv|flac|aac|ac3|eac3|dts|opus|mp3|dual ?audio|multi ?subs?|uncensored'
    r'|uncut|repack|proper)(?![a-z0-9])')


def _strip_language_suffix(stem: str) -> str:
    """'Suzume.ar' -> 'Suzume': a trailing '.xx' / '.xxx' language code (how
    players name external subtitles) is not part of the title."""
    head, dot, tail = stem.rpartition(".")
    if dot and head and 2 <= len(tail) <= 3 and tail.isalpha():
        code = _normalize_language(tail)
        if code in _LANGUAGE_NAMES and code != "und":
            return head
    return stem


def numberless_title(info: EpisodeInfo) -> str:
    """The name of a file without an episode number, reduced to what identifies
    it: no bracket/paren tags, release tags, trailing language code or case."""
    stem = info.filepath.stem
    if is_synced_copy(info.filepath):
        stem = stem[:-len(_SYNCED_SUFFIX)]
    stem = _strip_language_suffix(stem)
    stem = re.sub(r'\[.*?\]|\(.*?\)', ' ', stem).lower()
    stem = re.sub(r'[\W_]+', ' ', stem)
    stem = _RELEASE_TAGS.sub(' ', stem)
    return " ".join(stem.split())


def _match_key(info: EpisodeInfo) -> Optional[tuple]:
    """Files pair up only when this key is equal; None = never paired.

    With an episode number: same kind of extra ('' for an episode) and number.
    Without one (a film, 'Show - ED', 'Show OVA'): same kind and the same title.
    The two kinds of key never compare equal, so a numbered episode never pairs
    with a numberless subtitle or the other way round.
    """
    if info.episode_num:
        return ("episode", info.extra_kind, info.episode_num)
    title = numberless_title(info)
    if not title:
        return None
    return ("named", info.extra_kind, title)


def _superseded_originals(subtitles: Iterable[EpisodeInfo]) -> set[Path]:
    """Originals that have a '.synced' copy next to them: the copy replaces them."""
    by_name = {(s.filepath.parent, s.filepath.name.lower()): s.filepath for s in subtitles}
    replaced = set()
    for sub in subtitles:
        if is_synced_copy(sub.filepath):
            original = sub.filepath.stem[:-len(_SYNCED_SUFFIX)] + sub.filepath.suffix
            hit = by_name.get((sub.filepath.parent, original.lower()))
            if hit is not None:
                replaced.add(hit)
    return replaced


def match_files(videos: list[EpisodeInfo], subtitles: list[EpisodeInfo]) -> tuple[list[EpisodeMatch], list[EpisodeInfo], list[EpisodeInfo]]:
    """Match videos to subtitles by episode number.

    The episode number (and season, when both names state one) decides WHETHER two
    files pair up. The title similarity only picks between several candidates and
    is reported as the score: fansub groups use different romanisations and
    translated titles for the same show, so a different title lowers the
    confidence but never blocks a match.
    """
    matches = []
    unmatched_videos = []

    superseded = _superseded_originals(subtitles)
    sub_map: dict[tuple, list[EpisodeInfo]] = {}
    unmatched_subtitles = []
    for sub in subtitles:
        if sub.filepath in superseded:
            continue
        key = _match_key(sub)
        if key is None:
            unmatched_subtitles.append(sub)
        else:
            sub_map.setdefault(key, []).append(sub)

    # Plain episodes choose first: a video whose name carries a marker word that
    # was not recognised as an extra can never take the subtitle away from the
    # plain 'Show - 01.mkv'. The matches keep the order of `videos`.
    order = sorted(range(len(videos)), key=lambda i: _has_marker_word(videos[i].filepath.stem))
    by_index: dict[int, EpisodeMatch] = {}
    for index in order:
        vid = videos[index]
        key = _match_key(vid)
        candidates = [
            sub for sub in sub_map.get(key, [])
            if vid.season is None or sub.season is None or vid.season == sub.season
        ] if key is not None else []
        if not candidates:
            # Still listed in matches so the UI shows the episode, and reported
            # as unmatched so it can warn about it.
            by_index[index] = EpisodeMatch(
                video=vid,
                subtitle=None,
                confidence=MatchConfidence.NO_MATCH,
                score=0.0
            )
            continue

        # Closest title first; between equals the higher release version
        # ('01v2' over '01'), then a synced copy
        scored = [(title_similarity(vid, sub), sub.version, is_synced_copy(sub.filepath), sub)
                  for sub in candidates]
        score, _, _, best_sub = max(scored, key=lambda item: item[:3])

        by_index[index] = EpisodeMatch(
            video=vid,
            subtitle=best_sub,
            confidence=_confidence(vid, best_sub, score),
            score=score
        )
        # Remove matched sub from map to prevent double matching
        sub_map[key].remove(best_sub)

    for index, vid in enumerate(videos):
        matches.append(by_index[index])
        if by_index[index].subtitle is None:
            unmatched_videos.append(vid)

    # Collect remaining unmatched subtitles
    for sub_list in sub_map.values():
        unmatched_subtitles.extend(sub_list)

    return matches, unmatched_videos, unmatched_subtitles

import re
from pathlib import Path
from typing import Iterable, Optional

try:
    import anitopy
    HAS_ANITOPY = True
except ImportError:
    HAS_ANITOPY = False

from rapidfuzz import fuzz
from core.models import EpisodeInfo, EpisodeMatch, MatchConfidence
from core.constants import VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS, EPISODE_PATTERNS
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


# Extras that are never an episode: a file such as 'Show - NCOP1.mkv' must not
# receive the subtitle of episode 1.
_NEVER_MATCHED_KINDS = frozenset({"NCOP", "NCED", "OP", "ED", "PV", "PREVIEW", "CM", "MENU", "TRAILER"})
# Extras that are numbered like episodes but are a separate run: 'Show OVA - 01'
# only pairs with a subtitle that is also marked OVA.
_SEPARATE_RUN_KINDS = frozenset({"OVA", "SPECIAL"})
_KIND_ALIASES = {
    "OPENING": "OP", "ENDING": "ED", "OAD": "OVA", "OAV": "OVA", "SP": "SPECIAL",
    "SPECIALS": "SPECIAL", "CREDITLESS": "NCOP",
}
# What anitopy does not classify itself
_EXTRA_WORDS = re.compile(
    r'(?<![A-Za-z])(NC[ ._-]?OP|NC[ ._-]?ED|Creditless|Menu|Trailer)(?![a-z])', re.IGNORECASE)
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


def _extra_kind(filename: str, anime_type) -> str:
    """'' for a normal episode, else the normalised kind of extra."""
    types = anime_type if isinstance(anime_type, (list, tuple)) else [anime_type]
    kinds = [str(t).strip().upper() for t in types if t]
    word = _EXTRA_WORDS.search(filename)
    if word:
        kinds.append(re.sub(r'[ ._-]', '', word.group(1).upper()))
    kinds = [_KIND_ALIASES.get(k, k) for k in kinds]
    for group in (_NEVER_MATCHED_KINDS, _SEPARATE_RUN_KINDS):
        for kind in kinds:
            if kind in group:
                return kind
    return ""


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
    anime_type = None

    if HAS_ANITOPY:
        parsed = anitopy.parse(parse_name) or {}
        episode_num = normalize_episode_num(parsed.get("episode_number"))
        series_title = parsed.get("anime_title")
        season = parsed.get("anime_season")
        anime_type = parsed.get("anime_type")

    season = _parse_season(parse_name, season)
    extra_kind = _extra_kind(parse_name, anime_type)

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
        if ext in VIDEO_EXTENSIONS:
            if is_tool_output(f):
                continue
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


def _match_key(info: EpisodeInfo) -> Optional[tuple[str, str]]:
    """Files pair up only when this key is equal; None = never paired."""
    if not info.episode_num or info.extra_kind in _NEVER_MATCHED_KINDS:
        return None
    return (info.extra_kind, info.episode_num)


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
    sub_map: dict[tuple[str, str], list[EpisodeInfo]] = {}
    unmatched_subtitles = []
    for sub in subtitles:
        if sub.filepath in superseded:
            continue
        key = _match_key(sub)
        if key is None:
            unmatched_subtitles.append(sub)
        else:
            sub_map.setdefault(key, []).append(sub)

    for vid in videos:
        key = _match_key(vid)
        candidates = [
            sub for sub in sub_map.get(key, [])
            if vid.season is None or sub.season is None or vid.season == sub.season
        ] if key is not None else []
        if not candidates:
            # Still listed in matches so the UI shows the episode, and reported
            # as unmatched so it can warn about it.
            matches.append(EpisodeMatch(
                video=vid,
                subtitle=None,
                confidence=MatchConfidence.NO_MATCH,
                score=0.0
            ))
            unmatched_videos.append(vid)
            continue

        # Closest title first; between equals a synced copy wins
        scored = [(title_similarity(vid, sub), is_synced_copy(sub.filepath), sub) for sub in candidates]
        score, _, best_sub = max(scored, key=lambda item: (item[0], item[1]))

        matches.append(EpisodeMatch(
            video=vid,
            subtitle=best_sub,
            confidence=_confidence(vid, best_sub, score),
            score=score
        ))
        # Remove matched sub from map to prevent double matching
        sub_map[key].remove(best_sub)

    # Collect remaining unmatched subtitles
    for sub_list in sub_map.values():
        unmatched_subtitles.extend(sub_list)

    return matches, unmatched_videos, unmatched_subtitles

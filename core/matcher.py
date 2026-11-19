import re
from pathlib import Path
from typing import Iterable, Optional

try:
    import anitopy
    HAS_ANITOPY = True
except ImportError:
    HAS_ANITOPY = False

from rapidfuzz import fuzz
from core.languages import (
    lookup as _lookup_language, name_of as _language_name, normalize as _normalize_language,
    same_language,
)
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


# '.en', '.eng', '.ara', '.en-US', '.Arabic' at the end of a subtitle name
_SUFFIX_TAG = re.compile(r'\.([A-Za-z]{2,12}(?:-[A-Za-z0-9]{2,8})?)$')
# Words that may follow the language inside a bracket: '[Arabic Subs]', '(English Sub)'
_SUB_WORDS = re.compile(r'[\s._-]+(?:subs?|subtitles?|subbed|cc|sdh|forced)$', re.IGNORECASE)


def _suffix_language(stem: str) -> str:
    """Language of a trailing '.xx' / '.xxx' / '.Name' (how players name
    external subtitles); '' when there is none."""
    match = _SUFFIX_TAG.search(stem)
    if not match or not stem[:match.start()].strip():
        return ""
    return _lookup_language(match.group(1))


def subtitle_language_tag(stem: str) -> str:
    """The language a subtitle's name says it is in ('ara', 'eng', ...), '' when
    the name does not say. Read from a trailing '.en' / '.ara' suffix, else from
    the last bracket that holds nothing but a language: '(English)', '[ENG]',
    '(عربي)', '[Arabic Subs]'."""
    if stem.lower().endswith(_SYNCED_SUFFIX):
        stem = stem[:-len(_SYNCED_SUFFIX)]
    return _suffix_language(stem) or _bracket_language(stem)


def _bracket_language(stem: str) -> str:
    for bracket in reversed(list(_BRACKET.finditer(stem))):
        tag = _lookup_language(_SUB_WORDS.sub("", bracket.group(1).strip()))
        if tag:
            return tag
    return ""


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

    language = ""
    if filepath.suffix.lower() in SUBTITLE_EXTENSIONS:
        language = subtitle_language_tag(parse_stem)

    return EpisodeInfo(
        filepath=filepath,
        filename=filename,
        episode_num=episode_num,
        series_title=series_title,
        season=season,
        extra_kind=extra_kind,
        version=version,
        language=language,
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
    if not video.episode_num and not subtitle.episode_num:
        # Films and other numberless files: compare the reduced names, so 'Suzume.ar'
        # and 'Suzume 2022 1080p' are the same title
        a = numberless_title(video)
        if a and a in (numberless_title(subtitle), numberless_title(subtitle, strip_language=False)):
            return 100.0
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
    """'Suzume.ar' -> 'Suzume': a trailing language code (how players name
    external subtitles) is not part of the title. Only applied to subtitle names:
    'Tenki.no.Ko.mkv' keeps its 'Ko'."""
    if _suffix_language(stem):
        return stem[:stem.rindex(".")]
    return stem


_YEAR = re.compile(r'(?<![a-z0-9])(?:19|20)\d\d(?![a-z0-9])')
# '...x265-GROUP': a scene release group glued to the last release tag
_TRAILING_GROUP = re.compile(r'(?<=[A-Za-z0-9\])])-[A-Za-z0-9]+$')


def _is_subtitle(info: EpisodeInfo) -> bool:
    return info.filepath.suffix.lower() in SUBTITLE_EXTENSIONS


def numberless_title(info: EpisodeInfo, strip_language: Optional[bool] = None) -> str:
    """The name of a file without an episode number, reduced to what identifies
    it: no bracket/paren tags, release tags, years, trailing release group,
    trailing language code (subtitles only) or case.

    strip_language: None = only for subtitle files."""
    stem = info.filepath.stem
    if is_synced_copy(info.filepath):
        stem = stem[:-len(_SYNCED_SUFFIX)]
    if strip_language is None:
        strip_language = _is_subtitle(info)
    if strip_language:
        stem = _strip_language_suffix(stem)
    group = _TRAILING_GROUP.search(stem)
    if group and _RELEASE_TAGS.search(_normalize_title(stem[:group.start()])):
        stem = stem[:group.start()]
    stem = re.sub(r'\[.*?\]|\(.*?\)', ' ', stem).lower()
    stem = re.sub(r'[\W_]+', ' ', stem)
    stem = _RELEASE_TAGS.sub(' ', stem)
    # Years go too ('Suzume 2022'), unless the year is the whole title ('1917')
    without_year = _YEAR.sub(' ', stem)
    if without_year.strip():
        stem = without_year
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


def _subtitle_keys(sub: EpisodeInfo) -> list[tuple[tuple, str]]:
    """(match key, language tag) under which a subtitle can pair.

    A numberless subtitle whose name ends in what reads as a language code is
    listed twice: 'Tenki.no.Ko.srt' pairs with 'Tenki.no.Ko.mkv' (where 'Ko' is
    part of the title, so no language is assumed) as well as with 'Tenki.no.mkv'
    (where it reads as Korean)."""
    key = _match_key(sub)
    if key is None:
        return []
    keys = [(key, sub.language)]
    if key[0] == "named":
        raw = numberless_title(sub, strip_language=False)
        if raw and raw != key[2]:
            keys.append((("named", sub.extra_kind, raw), _bracket_language(sub.filepath.stem)))
    return keys


def _language_rank(tag: str, wanted: str) -> int:
    """2 = tagged with the wanted language, 1 = untagged, 0 = tagged with another."""
    if not wanted or not tag or _normalize_language(wanted) == "und":
        return 1
    return 2 if same_language(tag, wanted) else 0


def language_warning(tag: str, wanted: str) -> str:
    """Why a pairing needs a look when the subtitle's name says another language."""
    if _language_rank(tag, wanted) != 0:
        return ""
    return (f"subtitle looks like {_language_name(tag)}, "
            f"track will be labelled {_language_name(wanted)}")


def _score_tier(score: float) -> int:
    """The confidence band of a title score: within a band the language decides."""
    return 2 if score >= 80 else 1 if score >= 50 else 0


def match_files(videos: list[EpisodeInfo], subtitles: list[EpisodeInfo],
                subtitle_language: str = "") -> tuple[list[EpisodeMatch], list[EpisodeInfo], list[EpisodeInfo]]:
    """Match videos to subtitles by episode number.

    The episode number (and season, when both names state one) decides WHETHER two
    files pair up. The title similarity only picks between several candidates and
    is reported as the score: fansub groups use different romanisations and
    translated titles for the same show, so a different title lowers the
    confidence but never blocks a match.

    Every possible pair of a match key is ranked and the best pairs are taken
    first, whatever the order of the files: '5 Centimeters per Second.mkv' (read
    as episode 5) never takes 'Show - 05.srt' from 'Show - 05.mkv'. Ranking, best
    first: a video without a stray marker word; a subtitle not tagged with another
    language than `subtitle_language`; the title-score band; tagged with the
    wanted language over untagged; the exact score; the release version; a
    synced copy.
    """
    superseded = _superseded_originals(subtitles)
    usable = [sub for sub in subtitles if sub.filepath not in superseded]
    by_key: dict[tuple, list[tuple[EpisodeInfo, str]]] = {}
    for sub in usable:
        for key, tag in _subtitle_keys(sub):
            by_key.setdefault(key, []).append((sub, tag))

    pairs = []
    for index, vid in enumerate(videos):
        key = _match_key(vid)
        if key is None:
            continue
        plain = not _has_marker_word(vid.filepath.stem)
        for sub, tag in by_key.get(key, []):
            if vid.season is not None and sub.season is not None and vid.season != sub.season:
                continue
            score = title_similarity(vid, sub)
            rank = _language_rank(tag, subtitle_language)
            order = (plain, rank > 0, _score_tier(score), rank, score, sub.version,
                     is_synced_copy(sub.filepath))
            pairs.append((order, index, sub, tag, score))
    # Stable: between equal pairs the file order (by name) decides
    pairs.sort(key=lambda pair: pair[0], reverse=True)

    by_index: dict[int, EpisodeMatch] = {}
    used: set[int] = set()
    for _, index, sub, tag, score in pairs:
        if index in by_index or id(sub) in used:
            continue
        vid = videos[index]
        by_index[index] = EpisodeMatch(
            video=vid,
            subtitle=sub,
            confidence=_confidence(vid, sub, score),
            score=score,
            subtitle_language=tag,
            language_warning=language_warning(tag, subtitle_language),
        )
        used.add(id(sub))

    matches, unmatched_videos = [], []
    for index, vid in enumerate(videos):
        match = by_index.get(index)
        if match is None:
            # Still listed in matches so the UI shows the episode, and reported
            # as unmatched so it can warn about it.
            match = EpisodeMatch(video=vid, subtitle=None,
                                 confidence=MatchConfidence.NO_MATCH, score=0.0)
            unmatched_videos.append(vid)
        matches.append(match)

    unmatched_subtitles = [sub for sub in usable if id(sub) not in used]
    return matches, unmatched_videos, unmatched_subtitles


def unused_subtitles(matches: list[EpisodeMatch], subtitles: list[EpisodeInfo]) -> list[EpisodeInfo]:
    """The subtitles no episode uses (originals replaced by a synced copy left out)."""
    superseded = _superseded_originals(subtitles)
    used = {m.subtitle.filepath for m in matches if m.subtitle is not None}
    return [s for s in subtitles if s.filepath not in used and s.filepath not in superseded]


def set_manual_subtitle(matches: list[EpisodeMatch], index: int, subtitle: Optional[EpisodeInfo],
                        subtitle_language: str = "") -> Optional[int]:
    """Give episode `index` the subtitle the user picked (None = no subtitle).

    A subtitle goes to one episode only: when another episode had it, that
    episode is left without a subtitle and its index is returned."""
    moved_from = None
    if subtitle is not None:
        for i, other in enumerate(matches):
            if i != index and other.subtitle is not None and other.subtitle.filepath == subtitle.filepath:
                matches[i] = EpisodeMatch(video=other.video, subtitle=None,
                                          confidence=MatchConfidence.MANUAL, score=0.0)
                moved_from = i
    video = matches[index].video
    if subtitle is None:
        matches[index] = EpisodeMatch(video=video, subtitle=None,
                                      confidence=MatchConfidence.MANUAL, score=0.0)
    else:
        matches[index] = EpisodeMatch(
            video=video, subtitle=subtitle, confidence=MatchConfidence.MANUAL,
            score=title_similarity(video, subtitle),
            subtitle_language=subtitle.language,
            language_warning=language_warning(subtitle.language, subtitle_language))
    return moved_from

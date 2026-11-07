import re
from pathlib import Path
from typing import Optional

try:
    import anitopy
    HAS_ANITOPY = True
except ImportError:
    HAS_ANITOPY = False

from rapidfuzz import fuzz
from core.models import EpisodeInfo, EpisodeMatch, MatchConfidence
from core.constants import VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS, EPISODE_PATTERNS
from utils.logger import get_logger

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


def normalize_episode_num(value) -> Optional[str]:
    """Return a canonical episode number so '01', '1' and '001' compare equal.

    anitopy returns a list for multi-episode files ('01-02'); the first one is used.
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


def extract_episode_info(filepath: Path) -> EpisodeInfo:
    """Parse filename using anitopy first, then regex fallback patterns."""
    filename = filepath.name
    episode_num = None
    series_title = None

    if HAS_ANITOPY:
        parsed = anitopy.parse(filename)
        episode_num = normalize_episode_num(parsed.get("episode_number"))
        series_title = parsed.get("anime_title")

    # Fallback to regex patterns if anitopy failed or is not installed
    if not episode_num:
        for pattern in EPISODE_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                episode_num = normalize_episode_num(match.group(1))
                break

    if not episode_num:
        # Final fallback: any standalone number, after removing bracketed tags,
        # the extension and numbers that are clearly not episodes (1080p, x264, 2004...).
        cleaned = re.sub(r'\[.*?\]|\(.*?\)', ' ', filepath.stem)
        cleaned = _NON_EPISODE_NUMBERS.sub(' ', cleaned)
        match = re.search(r'(?<!\d)(\d{1,4})(?!\d)', cleaned)
        if match:
            episode_num = normalize_episode_num(match.group(1))

    # Try to clean up series title if missing
    if not series_title:
        # Basic heuristic: text before episode number or first bracket
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', filename)
        match = re.match(r'^(.*?)(?:-\s*\d|\s+\d|_+\d)', clean_name)
        if match:
            series_title = match.group(1).strip()
        else:
            series_title = clean_name.strip()

    return EpisodeInfo(
        filepath=filepath,
        filename=filename,
        episode_num=episode_num,
        series_title=series_title
    )

def scan_folder(folder_path: Path) -> tuple[list[EpisodeInfo], list[EpisodeInfo]]:
    """Scan folder for video and subtitle files."""
    videos = []
    subtitles = []
    
    if not folder_path.exists() or not folder_path.is_dir():
        logger.error(f"Invalid directory: {folder_path}")
        return videos, subtitles

    for item in folder_path.iterdir():
        if item.is_file():
            ext = item.suffix.lower()
            if ext in VIDEO_EXTENSIONS:
                videos.append(extract_episode_info(item))
            elif ext in SUBTITLE_EXTENSIONS:
                subtitles.append(extract_episode_info(item))
                
    return videos, subtitles

def auto_detect_series_name(episode_infos: list[EpisodeInfo]) -> str:
    """Try to detect series name from filenames."""
    titles = [info.series_title for info in episode_infos if info.series_title]
    if not titles:
        return "Unknown Series"
        
    # Find most common title
    from collections import Counter
    counts = Counter(titles)
    return counts.most_common(1)[0][0]

def match_files(videos: list[EpisodeInfo], subtitles: list[EpisodeInfo]) -> tuple[list[EpisodeMatch], list[EpisodeInfo], list[EpisodeInfo]]:
    """Match videos to subtitles by episode number, using rapidfuzz for disambiguation."""
    matches = []
    unmatched_videos = []
    
    # Group subtitles by episode number
    sub_map: dict[str, list[EpisodeInfo]] = {}
    for sub in subtitles:
        if sub.episode_num:
            sub_map.setdefault(sub.episode_num, []).append(sub)
            
    unmatched_subtitles = [sub for sub in subtitles if not sub.episode_num]
            
    for vid in videos:
        candidates = sub_map.get(vid.episode_num, []) if vid.episode_num else []
        if not candidates:
            # Still listed in matches (so the track cleanup can run without a new
            # subtitle), but also reported as unmatched so the UI can warn about it.
            matches.append(EpisodeMatch(
                video=vid,
                subtitle=None,
                confidence=MatchConfidence.NO_MATCH,
                score=0.0
            ))
            unmatched_videos.append(vid)
            continue
            
        if len(candidates) == 1:
            best_sub = candidates[0]
            confidence = MatchConfidence.HIGH
            score = 100.0
        else:
            # Disambiguate using fuzzy matching on filename
            best_sub = None
            best_score = -1
            for sub in candidates:
                score = fuzz.token_sort_ratio(vid.filename, sub.filename)
                if score > best_score:
                    best_score = score
                    best_sub = sub
                    
            if best_score > 80:
                confidence = MatchConfidence.HIGH
            elif best_score > 60:
                confidence = MatchConfidence.MEDIUM
            else:
                confidence = MatchConfidence.LOW
            score = best_score
            
        matches.append(EpisodeMatch(
            video=vid,
            subtitle=best_sub,
            confidence=confidence,
            score=score
        ))
        # Remove matched sub from map to prevent double matching
        sub_map[vid.episode_num].remove(best_sub)

    # Collect remaining unmatched subtitles
    for sub_list in sub_map.values():
        unmatched_subtitles.extend(sub_list)
        
    return matches, unmatched_videos, unmatched_subtitles

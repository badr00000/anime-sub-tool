"""Remakes and films told apart by year (two shows that differ only by year)."""

import itertools
from pathlib import Path

import pytest

from core.matcher import extract_episode_info, match_files


def _pairs(names, language="ara"):
    videos = [extract_episode_info(Path(n)) for n in names if n.endswith(".mkv")]
    subs = [extract_episode_info(Path(n)) for n in names if not n.endswith(".mkv")]
    matches, _, _ = match_files(videos, subs, language)
    return {m.video.filename: (m.subtitle.filename if m.subtitle else None) for m in matches}


def _every_order(names):
    results = {tuple(sorted(_pairs(list(order)).items())) for order in itertools.permutations(names)}
    assert len(results) == 1, "the result depends on the file order"
    return dict(next(iter(results)))


@pytest.mark.parametrize("names, expected", [
    # Only the 2019 remake has a subtitle: it must not go to the 2001 one
    (["[DB] Fruits Basket (2001) - 05 [DVD].mkv",
      "[Erai-raws] Fruits Basket (2019) - 05 [1080p].mkv",
      "Fruits Basket (2019) - 05.ar.ass"],
     {"[DB] Fruits Basket (2001) - 05 [DVD].mkv": None,
      "[Erai-raws] Fruits Basket (2019) - 05 [1080p].mkv": "Fruits Basket (2019) - 05.ar.ass"}),
    (["Hunter x Hunter (1999) - 01.mkv", "Hunter x Hunter (2011) - 01.mkv",
      "Hunter x Hunter 2011 - 01.ar.srt"],
     {"Hunter x Hunter (1999) - 01.mkv": None,
      "Hunter x Hunter (2011) - 01.mkv": "Hunter x Hunter 2011 - 01.ar.srt"}),
    # Both remakes have subtitles
    (["Urusei Yatsura (1981) - 01.mkv", "Urusei Yatsura (2022) - 01.mkv",
      "Urusei Yatsura (1981) - 01.srt", "Urusei Yatsura (2022) - 01.srt"],
     {"Urusei Yatsura (1981) - 01.mkv": "Urusei Yatsura (1981) - 01.srt",
      "Urusei Yatsura (2022) - 01.mkv": "Urusei Yatsura (2022) - 01.srt"}),
    # Films sharing a title
    (["Blade Runner (1982).mkv", "Blade Runner 2049 (2017).mkv", "Blade Runner 2049 (2017).ar.srt"],
     {"Blade Runner (1982).mkv": None,
      "Blade Runner 2049 (2017).mkv": "Blade Runner 2049 (2017).ar.srt"}),
])
def test_remakes_and_films_are_kept_apart_by_year(names, expected):
    assert _every_order(names) == expected


@pytest.mark.parametrize("names, expected_sub", [
    # A year on one side only is no conflict
    (["Fruits Basket - 05.mkv", "Fruits Basket (2019) - 05.ar.srt"], "Fruits Basket (2019) - 05.ar.srt"),
    (["Fruits Basket (2019) - 05.mkv", "Fruits Basket - 05.ar.srt"], "Fruits Basket - 05.ar.srt"),
    # Same year written differently
    (["Show 2023 - 01.mkv", "Show (2023) - 01.ar.srt"], "Show (2023) - 01.ar.srt"),
    # A year-like episode number is not a stated year
    (["Show - 2023.mkv", "Show (2020) - 2023.srt"], "Show (2020) - 2023.srt"),
    # Scene film name with title-year and release year
    (["2012.2009.1080p.BluRay.x264-GRP.mkv", "2012.srt"], "2012.srt"),
    (["Perfect Blue 1997.mkv", "Perfect Blue 1997.ar.srt"], "Perfect Blue 1997.ar.srt"),
])
def test_years_do_not_block_ordinary_pairs(names, expected_sub):
    assert list(_pairs(names).values()) == [expected_sub]

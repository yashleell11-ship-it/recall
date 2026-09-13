"""The corpus fetcher.

It runs on the VPS with a bare `python3` — no virtualenv, no dependencies — so
its first property is that it needs nothing to import. The second is that it
notices when the manifest is describing a PART and the URL is serving a WHOLE.
"""

import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fetch_corpus import (  # noqa: E402
    FORBIDDEN_HOSTS,
    warn_if_bigger_than_claimed,
)


def test_the_fetcher_imports_with_nothing_installed():
    """It is run as `python3 scripts/fetch_corpus.py` on a box with no venv, so a
    third-party import would break it there and nowhere else. This also keeps
    `httpx` confined to llm/client.py, which test_boundaries.py guards for src/."""
    text = (SCRIPTS / "fetch_corpus.py").read_text()
    for banned in ("import httpx", "import requests", "from httpx", "import fitz",
                   "import numpy", "from recall"):
        assert banned not in text, banned


def test_the_forbidden_hosts_are_shared_with_the_validator():
    """Imported from validate_corpus.py rather than restated, so the two cannot
    come to disagree about where material may not come from."""
    assert FORBIDDEN_HOSTS
    validator = (SCRIPTS / "validate_corpus.py").read_text()
    assert "FORBIDDEN_HOSTS" in validator


# (label, bytes on disk, pages the manifest claims). Every number measured on
# 2026-09-13 from the files the fetcher actually downloaded.
REAL_DOWNLOADS = (
    # The one that taught us: the manifest says chapter 7, 40 pages, but its
    # source_url is Entrepreneurship-WEB.pdf — the complete volume. 631 pages
    # landed under a chapter's name, and INT335 unit 6's pool became 732 of its
    # ~1000 chunks from one mismapped book.
    ("entrepreneurship 'ch7'", 129375799, 40, True),
    # ...and the ones that must stay quiet, including three that share that very
    # same whole-book URL and only escaped because the right file already existed.
    ("entrepreneurship ch4", 9000179, 32, False),
    ("entrepreneurship ch6", 8914264, 32, False),
    ("psychology2e ch7", 1979422, 34, False),
    ("intro to computer science, whole", 56261511, 939, False),
    ("calculus volume 1, whole", 52104540, 769, False),
    ("calculus volume 2, whole", 47350759, 737, False),
)


def test_the_guard_fires_on_the_mismapped_file_and_nothing_else():
    for label, size, pages, should_warn in REAL_DOWNLOADS:
        warning = warn_if_bigger_than_claimed(b"x" * size, "x.pdf", pages)
        assert (warning is not None) is should_warn, (label, warning)


def test_the_guard_says_what_it_saw():
    """A warning nobody can act on is noise. It names the size, the claim, and
    the ratio, so the reader can judge it without re-running anything."""
    warning = warn_if_bigger_than_claimed(b"x" * 129375799, "x.pdf", 40)
    assert "40 claimed pages" in warning
    assert "MB/page" in warning
    assert "whole volume" in warning


def test_a_missing_or_nonsense_page_count_is_not_an_error():
    """Most manifest lines carry `pages`, but the guard must not be the reason a
    line without one fails to fetch."""
    for pages in (None, 0, -3, "", "forty", {}):
        assert warn_if_bigger_than_claimed(b"x" * 99_000_000, "x.pdf", pages) is None


def test_it_warns_rather_than_rejects():
    """A fetcher that refuses real material is worse than a noisy one — the file
    may well be what is wanted, as this one is: the book does contain chapter 7.
    So the check returns a note and the download is kept."""
    import inspect

    import fetch_corpus

    source = inspect.getsource(fetch_corpus.fetch_one)
    # The warning is computed and returned, never raised.
    assert "warn_if_bigger_than_claimed" in source
    assert "raise FetchError" not in source.split("warn_if_bigger_than_claimed")[1]

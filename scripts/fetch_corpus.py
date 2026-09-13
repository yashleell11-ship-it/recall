#!/usr/bin/env python3
"""Fetch the corpus files that `manifest.jsonl` describes but disk does not have.

The manifest is written by the research pass — one line per source, with the
URL it came from and the licence it carries. Collecting the actual bytes is a
separate, resumable step, and it had drifted badly: 661 lines described, 97
files present. Four subjects (CSE326, INT108, CSE111, MEC103) had no corpus at
all, which is why no lesson could be written for them — a lesson only reaches
`grounded` by quoting a real file verbatim.

Stdlib only, deliberately. It runs with bare `python3` on the VPS without the
venv or the container, and it keeps `httpx` confined to `llm/client.py` where
`tests/test_boundaries.py` insists it stays.

Three things it will not do, each one a specific way a corpus goes bad:

1. **Leave a truncated file that looks complete.** Downloads land in a temp
   file and are renamed into place only once finished, so a killed run leaves
   nothing to mistake for a good download. Re-running resumes.
2. **Save an error page as a textbook.** An HTTP error that still returns 200
   with an HTML apology is the classic one. A file declared `.pdf` must
   actually start with `%PDF`, or it is rejected and reported rather than
   written.
3. **Fetch from a forbidden host.** The same list `validate_corpus.py` checks
   against, imported rather than copied so the two cannot drift.

Usage:
    python3 scripts/fetch_corpus.py /srv/recall/corpus --dry-run
    python3 scripts/fetch_corpus.py /srv/recall/corpus --subject CSE326
    python3 scripts/fetch_corpus.py /srv/recall/corpus --budget-mb 500
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_corpus import FORBIDDEN_HOSTS  # noqa: E402  (sibling script, stdlib only)

# Some publishers (NCERT, a few college sites) refuse a bare urllib UA.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
TIMEOUT_S = 60
RETRIES = 2
DELAY_S = 0.5  # be polite; these are free services doing us a favour

# A PDF that does not start with this is not a PDF, whatever the URL said.
PDF_MAGIC = b"%PDF"
# Below this, an HTML file is almost certainly an error or consent page.
# Matches validate_corpus.py's own "suspiciously small" threshold.
TINY_BYTES = 20_000


class FetchError(Exception):
    """A single file failed. Reported, never fatal to the run."""


def load_manifest(root: Path) -> list[dict]:
    path = root / "manifest.jsonl"
    if not path.exists():
        raise SystemExit(f"no manifest at {path}")
    entries = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"  manifest line {i}: invalid JSON, skipped — {exc}")
    return entries


def check_host(url: str) -> None:
    host = urlparse(url).netloc.lower()
    if host in FORBIDDEN_HOSTS:
        raise FetchError(f"forbidden host {host}")


def looks_like_what_it_claims(data: bytes, rel_path: str) -> None:
    """Reject an error page wearing a textbook's extension."""
    suffix = Path(rel_path).suffix.lower()
    if not data:
        raise FetchError("empty response")
    if suffix == ".pdf" and not data.lstrip()[:8].startswith(PDF_MAGIC):
        head = data.lstrip()[:60].decode("utf-8", "replace")
        raise FetchError(f"not a PDF (starts with {head!r})")
    if suffix in (".html", ".htm") and len(data) < TINY_BYTES:
        raise FetchError(f"suspiciously small HTML, {len(data)} bytes — likely an error page")


#: Above this many bytes per page the manifest's page count is not describing
#: this file. Measured on the entry that taught us: INT335's
#: "openstax-entrepreneurship-ch7-pitching-the-idea.pdf" declares 40 pages, but
#: its source_url is Entrepreneurship-WEB.pdf — the complete volume — so 129 MB
#: and 631 pages landed under a chapter's name, and INT335 unit 6's passage pool
#: became 732 of its ~1000 chunks from one mismapped book.
#:
#: The fetcher was right and the manifest was wrong, which is exactly the case a
#: size check can see and a magic-byte check cannot. Three sibling entries share
#: that whole-book URL — the two other Entrepreneurship chapters and a Psychology
#: one, all declaring 32-34 pages — and escaped only because per-chapter files
#: already existed on disk. Delete those and the next run pulls three more whole
#: textbooks onto a disk that shares 38 GB with manhwamaniacs.
#:
#: 1 MB/page is deliberately loose: an image-heavy OpenStax chapter runs at
#: 0.28 MB/page and the full 939-page computer-science volume at 0.06, while the
#: mismapped entry is at 3.2. A warning, not a rejection — the file may still be
#: wanted, and a fetcher that refuses real material is worse than a noisy one.
BYTES_PER_PAGE_WARN = 1024 * 1024


def warn_if_bigger_than_claimed(data: bytes, rel_path: str, pages: object) -> str | None:
    """A note when the download is far too large for the pages claimed."""
    try:
        claimed = int(pages)
    except (TypeError, ValueError):
        return None
    if claimed <= 0:
        return None
    per_page = len(data) / claimed
    if per_page < BYTES_PER_PAGE_WARN:
        return None
    return (f"{len(data) / 1024 / 1024:.0f} MB for {claimed} claimed pages "
            f"({per_page / 1024 / 1024:.1f} MB/page) — the source_url probably "
            f"serves a whole volume, not this one part of it")


def fetch_one(url: str, dest: Path, pages: object = None) -> tuple[int, str | None]:
    """Download to `dest` atomically. Returns (bytes written, warning or None)."""
    check_host(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    data: bytes | None = None
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                data = response.read()
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(1.5 * (attempt + 1))

    if data is None:
        raise FetchError(str(last))

    looks_like_what_it_claims(data, str(dest))
    warning = warn_if_bigger_than_claimed(data, str(dest), pages)

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Temp-then-rename: a killed run must not leave a partial file that the
    # next run counts as already downloaded.
    temp = dest.with_suffix(dest.suffix + ".part")
    temp.write_bytes(data)
    temp.rename(dest)
    return len(data), warning


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="~/recall-corpus")
    parser.add_argument("--subject", help="Only this subject code (e.g. CSE326).")
    parser.add_argument("--limit", type=int, help="Stop after this many files.")
    parser.add_argument(
        "--budget-mb",
        type=float,
        default=1500.0,
        help="Stop once this many megabytes have been downloaded (default 1500). "
        "The VPS shares a disk with manhwamaniacs; an unbounded fetch is how "
        "that disk fills.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List what would be fetched.")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    entries = load_manifest(root)

    pending = []
    for entry in entries:
        rel = str(entry.get("path", ""))
        if not rel or not entry.get("source_url"):
            continue
        if args.subject and entry.get("subject") != args.subject:
            continue
        if (root / rel).is_file():
            continue
        pending.append(entry)

    if args.limit:
        pending = pending[: args.limit]

    print(f"{len(entries)} manifest entries, {len(pending)} to fetch")
    if args.subject:
        print(f"filtered to subject {args.subject}")
    print(f"budget {args.budget_mb:.0f} MB\n")

    if args.dry_run:
        for entry in pending:
            print(f"  would fetch {entry['path']}")
            print(f"              {entry['source_url']}")
        return 0

    budget_bytes = args.budget_mb * 1024 * 1024
    downloaded = 0
    ok = 0
    failures: list[tuple[str, str]] = []
    oversized: list[tuple[str, str]] = []

    for i, entry in enumerate(pending, 1):
        rel = entry["path"]
        url = entry["source_url"]
        if downloaded >= budget_bytes:
            print(f"\nbudget reached ({downloaded / 1024 / 1024:.0f} MB) — stopping cleanly.")
            print(f"{len(pending) - i + 1} still pending; re-run to continue.")
            break
        try:
            size, warning = fetch_one(url, root / rel, entry.get("pages"))
            downloaded += size
            ok += 1
            print(f"[{i}/{len(pending)}] {rel}  {size / 1024:.0f} KB")
            if warning:
                oversized.append((rel, warning))
                print(f"              WARNING: {warning}")
        except FetchError as exc:
            failures.append((rel, str(exc)))
            print(f"[{i}/{len(pending)}] {rel}  FAILED: {exc}")
        except Exception as exc:  # noqa: BLE001 - one bad file must not end the run
            failures.append((rel, f"{type(exc).__name__}: {exc}"))
            print(f"[{i}/{len(pending)}] {rel}  FAILED: {type(exc).__name__}: {exc}")
        time.sleep(DELAY_S)

    print(f"\nfetched {ok}, failed {len(failures)}, {downloaded / 1024 / 1024:.1f} MB")

    if failures:
        report = root / "fetch-failures.txt"
        report.write_text(
            "\n".join(f"{rel}\t{why}" for rel, why in failures) + "\n", encoding="utf-8"
        )
        print(f"failures written to {report}")
        print("\nA failure here is usually a moved URL, not a bug. The manifest line")
        print("still describes a real source — re-find it or drop the line.")

    if oversized:
        print(f"\n{len(oversized)} file(s) came back far larger than the manifest's")
        print("page count implies. Nothing was rejected — the file may still be what")
        print("is wanted — but the manifest is describing a PART and the URL is")
        print("serving a WHOLE, so the filename now lies about its contents:")
        for rel, why in oversized:
            print(f"  {rel}\n      {why}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

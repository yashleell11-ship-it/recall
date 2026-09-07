#!/usr/bin/env python3
"""Sanity-check a collected corpus before it goes anywhere near `recall
ingest-corpus`.

Three checks, each one a real thing that went wrong while building corpora
before: a file present on disk with no manifest line describing it (so it
would sit there forever, silently never ingested); a manifest line whose file
is missing (a download that failed after the line was written); and a source
URL that traces back to a forbidden domain even though the licence field
looks fine (an agent copying the licence text without checking who actually
published it).

Usage: python3 scripts/validate_corpus.py [corpus_dir]
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

FORBIDDEN_HOSTS = {
    "scribd.com", "www.scribd.com",
    "studocu.com", "www.studocu.com",
    "coursehero.com", "www.coursehero.com",
    "chegg.com", "www.chegg.com",
    "collegesidekick.com", "www.collegesidekick.com",
    "docsity.com", "www.docsity.com",
}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "~/recall-corpus").expanduser()
    manifest_path = root / "manifest.jsonl"
    if not manifest_path.exists():
        print(f"no manifest at {manifest_path}")
        return 2

    manifest_lines = [
        l for l in manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    entries = []
    bad_json = 0
    for i, line in enumerate(manifest_lines, 1):
        try:
            entries.append((i, json.loads(line)))
        except json.JSONDecodeError as exc:
            bad_json += 1
            print(f"  line {i}: invalid JSON — {exc}")

    listed_paths: set[str] = set()
    missing_files, forbidden, no_licence = [], [], []
    for i, e in entries:
        rel = str(e.get("path", ""))
        listed_paths.add(rel)
        p = root / rel
        if not p.is_file():
            missing_files.append((i, rel))
        url = str(e.get("source_url", ""))
        if url:
            host = urlparse(url).netloc.lower()
            if host in FORBIDDEN_HOSTS:
                forbidden.append((i, rel, host))
        if not str(e.get("licence", "")).strip():
            no_licence.append((i, rel))

    on_disk = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.jsonl" and not p.name.startswith(".")
    }
    orphans = sorted(on_disk - listed_paths)

    tiny = [
        str(p.relative_to(root)) for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in (".pdf", ".html", ".htm")
        and p.stat().st_size < 20_000
    ]

    print(f"{len(manifest_lines)} manifest lines, {len(on_disk)} files on disk\n")

    def section(title, items, fmt=lambda x: str(x)):
        print(f"{title}: {len(items)}")
        for x in items[:15]:
            print("  -", fmt(x))
        if len(items) > 15:
            print(f"  ... and {len(items) - 15} more")
        print()

    section("Bad JSON lines", [], )  # already printed above
    section("Manifest entries whose file is missing", missing_files,
             lambda t: f"line {t[0]}: {t[1]}")
    section("Files on disk with no manifest line (orphans)", orphans)
    section("FORBIDDEN source domains slipped through", forbidden,
             lambda t: f"line {t[0]}: {t[1]} -> {t[2]}")
    section("Entries with no licence recorded", no_licence,
             lambda t: f"line {t[0]}: {t[1]}")
    section("Suspiciously small files (<20KB, likely an error page)", tiny)

    ok = not (bad_json or missing_files or forbidden)
    print("RESULT:", "clean enough to ingest" if ok else "fix the above first")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

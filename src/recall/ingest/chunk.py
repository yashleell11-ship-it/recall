import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page_ref: str


def _segments(pages: list[tuple[int, str]]) -> list[tuple[str, int]]:
    segs: list[tuple[str, int]] = []
    for page_no, text in pages:
        for part in _SENTENCE_END.split(text):
            part = part.strip()
            if part:
                segs.append((part, page_no))
    return segs


def _page_ref(first: int, last: int) -> str:
    return f"p{first}" if first == last else f"p{first}-p{last}"


def chunk_pages(
    pages: list[tuple[int, str]],
    target_chars: int = 3000,
    overlap_chars: int = 300,
) -> list[Chunk]:
    """Split pages into overlapping chunks on sentence boundaries."""
    segs = _segments(pages)
    chunks: list[Chunk] = []
    i = 0
    while i < len(segs):
        buf: list[tuple[str, int]] = []
        size = 0
        j = i
        while j < len(segs) and size < target_chars:
            buf.append(segs[j])
            size += len(segs[j][0]) + 1
            j += 1
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                text=" ".join(s for s, _ in buf),
                page_ref=_page_ref(buf[0][1], buf[-1][1]),
            )
        )
        if j >= len(segs):
            break
        # Step back for overlap, but never past i+1 or the loop cannot advance.
        k, back = j, 0
        while k > i + 1 and back < overlap_chars:
            k -= 1
            back += len(segs[k][0]) + 1
        i = k
    return chunks

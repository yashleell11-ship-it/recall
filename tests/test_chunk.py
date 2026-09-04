from recall.ingest.chunk import chunk_pages


def test_short_input_is_one_chunk():
    chunks = chunk_pages([(1, "A short sentence. Another one.")])
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].page_ref == "p1"


def test_long_input_splits_into_multiple_chunks():
    body = " ".join(f"Sentence number {i}." for i in range(400))
    chunks = chunk_pages([(1, body)], target_chars=500, overlap_chars=50)
    assert len(chunks) > 3
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunks_overlap():
    body = " ".join(f"Fact {i} is true." for i in range(200))
    chunks = chunk_pages([(1, body)], target_chars=400, overlap_chars=100)
    first_tail = set(chunks[0].text.split()[-8:])
    second_head = set(chunks[1].text.split()[:8])
    assert first_tail & second_head


def test_page_ref_spans_pages():
    pages = [(3, "Alpha sentence. " * 30), (4, "Beta sentence. " * 30)]
    chunks = chunk_pages(pages, target_chars=100_000)
    assert chunks[0].page_ref == "p3-p4"


def test_single_enormous_sentence_terminates():
    chunks = chunk_pages([(1, "x" * 20_000)], target_chars=500, overlap_chars=50)
    assert len(chunks) == 1
    assert chunks[0].text.startswith("x")


def test_blank_input_yields_nothing():
    assert chunk_pages([]) == []


def test_large_overlap_relative_to_target_still_terminates():
    body = " ".join(f"Sentence {i} here." for i in range(50))
    chunks = chunk_pages([(1, body)], target_chars=100, overlap_chars=500)
    assert len(chunks) >= 1

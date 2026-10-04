from app.services.chunking import chunk_text


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("", chunk_size=100, chunk_overlap=20) == []
    assert chunk_text("   \n\n  ", chunk_size=100, chunk_overlap=20) == []


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_text("A short sentence.", chunk_size=1000, chunk_overlap=150)
    assert len(chunks) == 1
    assert chunks[0].content == "A short sentence."
    assert chunks[0].index == 0
    assert chunks[0].char_count == len("A short sentence.")


def test_splits_on_paragraph_boundaries() -> None:
    text = "First paragraph." + "\n\n" + "Second paragraph." + "\n\n" + "Third paragraph."
    # chunk_size small enough that each paragraph becomes roughly its own chunk
    chunks = chunk_text(text, chunk_size=20, chunk_overlap=0)

    assert len(chunks) >= 2
    joined = " ".join(c.content for c in chunks)
    assert "First paragraph." in joined
    assert "Second paragraph." in joined
    assert "Third paragraph." in joined


def test_chunk_indices_are_sequential() -> None:
    text = "\n\n".join(f"Paragraph number {i} with some content in it." for i in range(10))
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)

    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_consecutive_chunks_share_overlap_content() -> None:
    text = "\n\n".join(f"Paragraph number {i} has unique content here." for i in range(8))
    chunks = chunk_text(text, chunk_size=120, chunk_overlap=40)

    assert len(chunks) >= 2
    # The overlap tail of chunk N should reappear at the start of chunk N+1.
    tail_of_first = chunks[0].content[-40:]
    assert tail_of_first[-10:] in chunks[1].content


def test_oversized_single_paragraph_is_split_on_sentences() -> None:
    long_paragraph = " ".join(f"This is sentence number {i}." for i in range(50))
    chunks = chunk_text(long_paragraph, chunk_size=200, chunk_overlap=20)

    assert len(chunks) > 1
    for chunk in chunks:
        # Bounded: individual chunks shouldn't wildly exceed chunk_size once
        # overlap is accounted for.
        assert chunk.char_count <= 200 + 20 + 50


def test_pathological_run_on_text_is_hard_split() -> None:
    # No sentence-ending punctuation anywhere — forces the last-resort
    # character hard-split path.
    run_on = "word " * 500
    chunks = chunk_text(run_on, chunk_size=100, chunk_overlap=10)

    assert len(chunks) > 1
    for chunk in chunks:
        # Bound includes the 2-char "\n\n" separator the packer inserts
        # between carried-over overlap text and the next unit — see
        # chunk_text's docstring ("bounded, not exact").
        assert chunk.char_count <= 100 + 10 + 2


def test_all_content_is_preserved_across_chunks() -> None:
    text = "\n\n".join(f"Distinctive marker {i} appears here." for i in range(6))
    chunks = chunk_text(text, chunk_size=80, chunk_overlap=15)

    combined = " ".join(c.content for c in chunks)
    for i in range(6):
        assert f"Distinctive marker {i}" in combined

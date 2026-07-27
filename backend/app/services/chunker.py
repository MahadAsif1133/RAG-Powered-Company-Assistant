from __future__ import annotations

from typing import List


# Target chunk size in characters (~500 tokens ≈ 2000 chars at ~4 chars/token)
DEFAULT_CHUNK_SIZE = 2000
# Overlap in characters (~50 tokens ≈ 200 chars)
DEFAULT_CHUNK_OVERLAP = 200

# Separator hierarchy: try splitting on double newline first, then single newline,
# then sentence boundary, then space. Avoids splitting mid-word.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """
    Recursively split `text` into chunks of approximately `chunk_size` characters
    with `chunk_overlap` character overlap.

    No external dependencies — implemented from scratch so the logic is easy to
    debug and explain in client demos.

    Returns a list of non-empty text strings.
    """
    text = text.strip()
    if not text:
        return []

    chunks = _recursive_split(text, chunk_size, chunk_overlap, SEPARATORS)
    # Final pass: filter empty strings and strip whitespace
    return [c.strip() for c in chunks if c.strip()]


def _recursive_split(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: List[str],
) -> List[str]:
    """
    Try splitting on the first separator. If any resulting piece is still too large,
    recurse with the next separator in the list.
    """
    if len(text) <= chunk_size:
        return [text]

    separator = separators[0]
    remaining_seps = separators[1:]

    if separator == "":
        # Last resort: hard split by character count
        return _hard_split(text, chunk_size, chunk_overlap)

    splits = text.split(separator)

    # Merge splits back together respecting chunk_size
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for split in splits:
        split_len = len(split)
        sep_len = len(separator)

        if current_len + split_len + (sep_len if current else 0) > chunk_size and current:
            # Flush current chunk
            chunk_text_str = separator.join(current)
            if len(chunk_text_str) > chunk_size and remaining_seps:
                # Chunk is still too big → recurse with finer separator
                chunks.extend(_recursive_split(chunk_text_str, chunk_size, chunk_overlap, remaining_seps))
            else:
                chunks.append(chunk_text_str)

            # Overlap: keep the last few pieces to maintain context
            overlap_pieces: List[str] = []
            overlap_len = 0
            for piece in reversed(current):
                if overlap_len + len(piece) + sep_len <= chunk_overlap:
                    overlap_pieces.insert(0, piece)
                    overlap_len += len(piece) + sep_len
                else:
                    break
            current = overlap_pieces
            current_len = overlap_len

        current.append(split)
        current_len += split_len + (sep_len if len(current) > 1 else 0)

    # Flush remaining
    if current:
        chunk_text_str = separator.join(current)
        if len(chunk_text_str) > chunk_size and remaining_seps:
            chunks.extend(_recursive_split(chunk_text_str, chunk_size, chunk_overlap, remaining_seps))
        else:
            chunks.append(chunk_text_str)

    return chunks


def _hard_split(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Brute-force character-level split as the last resort."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - chunk_overlap
    return chunks

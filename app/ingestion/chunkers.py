from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

Unit = tuple[str, dict]


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def fixed_size_chunker(units: list[Unit], chunk_size: int = 1000, overlap: int = 100) -> list[Chunk]:
    """Naive fixed-width character windows, ignoring sentence/section boundaries."""
    chunks: list[Chunk] = []
    for text, metadata in units:
        start = 0
        while start < len(text):
            end = start + chunk_size
            piece = text[start:end].strip()
            if piece:
                chunks.append(Chunk(piece, {**metadata, "chunk_strategy": "fixed"}))
            start += chunk_size - overlap
    return chunks


def recursive_chunker(units: list[Unit], chunk_size: int = 800, overlap: int = 100) -> list[Chunk]:
    """Cascades through separators (paragraph/sentence/word) to keep semantic boundaries intact."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[Chunk] = []
    for text, metadata in units:
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if piece:
                chunks.append(Chunk(piece, {**metadata, "chunk_strategy": "recursive"}))
    return chunks


def section_aware_chunker(units: list[Unit], max_chunk_size: int = 1200) -> list[Chunk]:
    """Keeps each pre-identified section (page / table block / sheet) as one chunk,
    only subdividing recursively when a section is too large to embed well."""
    chunks: list[Chunk] = []
    fallback_splitter = RecursiveCharacterTextSplitter(chunk_size=max_chunk_size, chunk_overlap=100)
    for text, metadata in units:
        text = text.strip()
        if not text:
            continue
        if len(text) <= max_chunk_size:
            chunks.append(Chunk(text, {**metadata, "chunk_strategy": "section_aware"}))
        else:
            for piece in fallback_splitter.split_text(text):
                piece = piece.strip()
                if piece:
                    chunks.append(Chunk(piece, {**metadata, "chunk_strategy": "section_aware"}))
    return chunks


CHUNKERS = {
    "fixed": fixed_size_chunker,
    "recursive": recursive_chunker,
    "section_aware": section_aware_chunker,
}


def chunk_units(units: list[Unit], strategy: str) -> list[Chunk]:
    if strategy not in CHUNKERS:
        raise ValueError(f"Unknown chunk strategy: {strategy}")
    return CHUNKERS[strategy](units)

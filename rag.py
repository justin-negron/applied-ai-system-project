"""Lightweight RAG retriever over the knowledge/ directory.

Chunks each markdown doc by `##` heading, then scores chunks using normalized
token overlap with the query (with a bonus when species/breed appears in the
chunk). Deterministic and dependency-free so it's easy to test and explain.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "its", "of", "on", "or", "that", "the", "to",
    "was", "were", "will", "with", "i", "my", "me", "you", "your", "we",
    "our", "what", "how", "do", "does", "should", "can", "if", "this", "but",
    "there", "their", "they", "them", "his", "her", "she", "he", "him",
}


@dataclass
class Chunk:
    source: str
    heading: str  # full display heading: "Doc Title — Section"
    section_heading: str  # just the section, used for scoring
    text: str

    def excerpt(self, max_chars: int = 600) -> str:
        if len(self.text) <= max_chars:
            return self.text
        return self.text[:max_chars].rsplit(" ", 1)[0] + "..."


@dataclass
class Retrieval:
    chunk: Chunk
    score: float


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in STOPWORDS and len(t) > 1}


def _load_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    if not KNOWLEDGE_DIR.exists():
        return chunks

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        # Split on `##` headings — first chunk gets the doc title from the `#` heading.
        sections = re.split(r"^##\s+", raw, flags=re.MULTILINE)
        title_match = re.match(r"^#\s+(.+)$", sections[0], flags=re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else path.stem

        # Section after the H1 (before any H2) — keep as an "Overview" chunk if non-trivial.
        intro = re.sub(r"^#\s+.+$", "", sections[0], count=1, flags=re.MULTILINE).strip()
        if intro:
            chunks.append(
                Chunk(
                    source=path.name,
                    heading=f"{doc_title} — Overview",
                    section_heading="Overview",
                    text=intro,
                )
            )

        for section in sections[1:]:
            section = section.strip()
            if not section:
                continue
            heading, _, body = section.partition("\n")
            body = body.strip()
            if body:
                chunks.append(
                    Chunk(
                        source=path.name,
                        heading=f"{doc_title} — {heading.strip()}",
                        section_heading=heading.strip(),
                        text=body,
                    )
                )
    return chunks


_CHUNK_CACHE: list[Chunk] | None = None


def _chunks() -> list[Chunk]:
    global _CHUNK_CACHE
    if _CHUNK_CACHE is None:
        _CHUNK_CACHE = _load_chunks()
    return _CHUNK_CACHE


def retrieve(
    query: str,
    species: Optional[str] = None,
    breed: Optional[str] = None,
    top_k: int = 2,
) -> list[Retrieval]:
    """Return the top_k most relevant chunks for a query.

    species/breed are optional filters that boost matching chunks (additive
    bonus, not a hard filter — a query about "exercise" still works without
    knowing the breed).
    """
    query_tokens = _tokenize(query)
    if species:
        query_tokens |= _tokenize(species)
    if breed:
        query_tokens |= _tokenize(breed)

    if not query_tokens:
        return []

    scored: list[Retrieval] = []
    for chunk in _chunks():
        heading_tokens = _tokenize(chunk.section_heading)
        body_tokens_list = re.findall(r"[a-z0-9]+", chunk.text.lower())
        body_tokens_filtered = [t for t in body_tokens_list if t not in STOPWORDS and len(t) > 1]
        if not body_tokens_filtered and not heading_tokens:
            continue

        # TF score: sum of how often each query token appears in the body.
        tf = sum(body_tokens_filtered.count(t) for t in query_tokens)
        # Heading boost: heading hits matter much more than body hits.
        heading_overlap = len(query_tokens & heading_tokens)

        score = tf + 5.0 * heading_overlap
        if score == 0:
            continue

        # Mild length normalization so a 1000-word chunk doesn't dominate.
        score = score / (1 + 0.01 * len(body_tokens_filtered))

        # Bonus when species/breed is explicitly present in heading or body.
        text_lower = (chunk.heading + " " + chunk.text).lower()
        if species and species.lower() in text_lower:
            score += 0.5
        if breed and breed.lower() in text_lower:
            score += 1.0

        scored.append(Retrieval(chunk=chunk, score=score))

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:top_k]


def format_retrievals(retrievals: list[Retrieval]) -> str:
    """Format retrievals as a readable string for the agent's tool result."""
    if not retrievals:
        return "No relevant guidelines found in the knowledge base."

    lines = []
    for i, r in enumerate(retrievals, 1):
        lines.append(f"[{i}] Source: {r.chunk.source} — {r.chunk.heading}")
        lines.append(f"    Relevance: {r.score:.2f}")
        lines.append(f"    {r.chunk.excerpt()}")
        lines.append("")
    return "\n".join(lines).strip()

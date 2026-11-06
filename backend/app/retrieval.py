import math
import re
from collections import Counter
from sqlalchemy.orm import Session
from .models import KnowledgeDocument


STOP_WORDS = {"the", "and", "for", "with", "that", "this", "from", "have", "please", "can", "my"}


def tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOP_WORDS]


def hybrid_search(db: Session, query: str, limit: int = 3, exclude_adversarial: bool = True) -> list[KnowledgeDocument]:
    """Deterministic hybrid retrieval using BM25-style text scores.

    This local implementation has no model or network dependency. The production
    provider boundary allows a vector backend to replace it without API changes.
    """
    rows = db.query(KnowledgeDocument).all()
    rows = [row for row in rows if not (exclude_adversarial and row.doc_id == "KB-ADVERSARIAL-001")]
    query_terms = tokens(query)
    corpus_lengths = [len(tokens(row.content)) for row in rows]
    average_length = sum(corpus_lengths) / max(len(corpus_lengths), 1)
    scored = []
    for row, length in zip(rows, corpus_lengths):
        counts = Counter(tokens(row.content))
        score = 0.0
        for term in set(query_terms):
            frequency = counts.get(term, 0)
            if frequency:
                document_frequency = sum(term in set(tokens(candidate.content)) for candidate in rows)
                inverse_frequency = math.log(1 + (len(rows) - document_frequency + 0.5) / (document_frequency + 0.5))
                score += inverse_frequency * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / max(average_length, 1)))
        title = tokens(row.title)
        score += sum(1.5 for term in set(query_terms) if term in title)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:limit]]

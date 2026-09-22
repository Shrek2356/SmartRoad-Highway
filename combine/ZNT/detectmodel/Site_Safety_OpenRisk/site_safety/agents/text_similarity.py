"""Small dependency-free character n-gram TF-IDF fallback for portable deployments."""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, List


def _ngrams(text: str) -> Counter[str]:
    compact = " ".join(text.lower().split())
    terms: Counter[str] = Counter()
    for size in (1, 2, 3):
        terms.update(compact[index:index + size] for index in range(max(0, len(compact) - size + 1)))
    return terms


class PortableCharTfidf:
    """Enough TF-IDF/cosine functionality for local regulation retrieval."""

    def __init__(self, documents: Iterable[str]) -> None:
        docs = list(documents)
        counters = [_ngrams(text) for text in docs]
        document_frequency: Counter[str] = Counter()
        for counter in counters:
            document_frequency.update(counter.keys())
        count = max(1, len(counters))
        self.idf = {
            term: math.log((1 + count) / (1 + frequency)) + 1.0
            for term, frequency in document_frequency.items()
        }
        self.documents = [self._normalise(counter) for counter in counters]

    def _normalise(self, counter: Counter[str]) -> dict[str, float]:
        weighted = {term: value * self.idf[term] for term, value in counter.items() if term in self.idf}
        norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
        return {term: value / norm for term, value in weighted.items()}

    def similarities(self, query: str) -> List[float]:
        vector = self._normalise(_ngrams(query))
        return [sum(value * document.get(term, 0.0) for term, value in vector.items()) for document in self.documents]

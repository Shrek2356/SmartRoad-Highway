"""规范条款语义检索器（可插拔后端）。

- 优先 sentence-transformers 语义向量（本机装有bge/m3e等中文模型时自动启用）；
- 缺省回退到字符n-gram TF-IDF余弦（sklearn，无需下载模型，对中文条款足够可用）；
- 精确关键词匹配仍由 RiskReasoningAgent.search_regulations 提供，
  语义检索作为"查不到精确词"时的兜底与扩展。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from site_safety.agents.schemas import RegulationRef


class RegulationRetriever:
    def __init__(
        self,
        regulations: Dict[str, RegulationRef],
        *,
        backend: str = "auto",
        st_model_name: str = "BAAI/bge-small-zh-v1.5",
    ) -> None:
        self.regulations = list(regulations.values())
        self.docs = [
            f"{r.name_zh} {r.clause} {r.requirement_zh}" for r in self.regulations
        ]
        self.backend = "none"
        if backend in {"auto", "sentence_transformers"}:
            try:  # pragma: no cover - 依赖本机模型
                from sentence_transformers import SentenceTransformer

                self._st = SentenceTransformer(st_model_name)
                self._doc_emb = self._st.encode(self.docs, normalize_embeddings=True)
                self.backend = "sentence_transformers"
            except Exception:
                pass
        if self.backend == "none":
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer

                # 字符1-3gram：无需分词即可覆盖中文词面与子词
                self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3))
                self._doc_mat = self._vectorizer.fit_transform(self.docs)
                self.backend = "tfidf_char_ngram"
            except Exception:
                from site_safety.agents.text_similarity import PortableCharTfidf

                self._portable_vectorizer = PortableCharTfidf(self.docs)
                self.backend = "portable_tfidf_char_ngram"

    def search(
        self, query: str, *, top_k: int = 8, min_score: float = 0.10
    ) -> List[Tuple[RegulationRef, float]]:
        query = query.strip()
        if not query or not self.regulations:
            return []
        if self.backend == "sentence_transformers":  # pragma: no cover
            import numpy as np

            q = self._st.encode([query], normalize_embeddings=True)[0]
            scores = np.asarray(self._doc_emb) @ q
        elif self.backend == "tfidf_char_ngram":
            try:
                from sklearn.metrics.pairwise import cosine_similarity

                q = self._vectorizer.transform([query])
                scores = cosine_similarity(q, self._doc_mat)[0]
            except Exception:
                from site_safety.agents.text_similarity import PortableCharTfidf

                self._portable_vectorizer = PortableCharTfidf(self.docs)
                self.backend = "portable_tfidf_char_ngram"
                scores = self._portable_vectorizer.similarities(query)
        else:
            scores = self._portable_vectorizer.similarities(query)
        ranked = sorted(
            zip(self.regulations, (float(s) for s in scores)),
            key=lambda item: item[1],
            reverse=True,
        )
        return [(reg, round(score, 4)) for reg, score in ranked[:top_k] if score >= min_score]

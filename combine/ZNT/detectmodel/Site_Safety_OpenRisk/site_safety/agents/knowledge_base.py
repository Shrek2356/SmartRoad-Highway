"""条款级RAG知识库：把任意安全规程文档扔进目录即可被检索。

用法：把 .md / .txt / .pdf / .docx 文件放入 knowledge_base/ 目录，
系统自动按标题与条款编号切块、建立索引；检索走与规范库相同的
本地TF-IDF字符n-gram后端（无远程模型下载）。
文件增删改后自动重建索引（按目录指纹判断）。
"""
from __future__ import annotations

import re
import json
import hashlib
import tempfile
import threading
from functools import wraps
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# 条款切分锚点：markdown标题 / "第x条|章|节" / "1.2.3"式编号
_CLAUSE_PATTERN = re.compile(
    r"^(#{1,6}\s+.+|第[一二三四五六七八九十百\d]+[条章节].*|\d+(?:\.\d+)+\s*.+)$",
    re.MULTILINE,
)
_MAX_CHUNK_CHARS = 600
_MIN_CHUNK_CHARS = 10


def _locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


@dataclass
class KnowledgeChunk:
    chunk_id: str
    source_file: str
    section: str
    text: str


def _read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return ""


def _split_clauses(text: str) -> List[Tuple[str, str]]:
    """按标题/条款编号切块，返回[(section标题, 正文)]；超长块再按空行细分。"""
    matches = list(_CLAUSE_PATTERN.finditer(text))
    blocks: List[Tuple[str, str]] = []
    if not matches:
        blocks = [("正文", text)]
    else:
        if matches[0].start() > 0:
            blocks.append(("前言", text[: matches[0].start()]))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = match.group(0).lstrip("# ").strip()
            blocks.append((section, text[match.end():end]))
    chunks: List[Tuple[str, str]] = []
    for section, body in blocks:
        body = body.strip()
        content = f"{section}\n{body}" if body else section
        if len(content) < _MIN_CHUNK_CHARS:
            continue
        if len(content) <= _MAX_CHUNK_CHARS:
            chunks.append((section, content))
        else:  # 超长条款按空行二次切分
            part = ""
            for paragraph in re.split(r"\n\s*\n", content):
                if len(part) + len(paragraph) > _MAX_CHUNK_CHARS and part:
                    chunks.append((section, part.strip()))
                    part = ""
                part += paragraph + "\n\n"
            if part.strip():
                chunks.append((section, part.strip()))
    return chunks


class KnowledgeBase:
    def __init__(self, kb_dir: str | Path) -> None:
        self._lock = threading.RLock()
        self.kb_dir = Path(kb_dir)
        self.chunks: List[KnowledgeChunk] = []
        self.sources = {}
        self._fingerprint: Optional[tuple] = None
        self._retriever = None
        self.refresh()

    @_locked
    def import_document(self, filename: str, content: bytes) -> int:
        """Validate staged content before atomically replacing an existing document."""
        if Path(filename).name != filename or Path(filename).suffix.lower() not in {".txt", ".md", ".pdf", ".docx"}:
            raise ValueError("规范文件名或格式无效")
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        target = self.kb_dir / filename
        previous = target.read_bytes() if target.is_file() else None
        with tempfile.TemporaryDirectory(prefix=".import-", dir=self.kb_dir) as staging:
            candidate = Path(staging) / filename
            candidate.write_bytes(content)
            if not _split_clauses(_read_document(candidate)):
                raise ValueError("文件未解析出有效文本，请检查PDF是否为扫描件或文档内容是否为空；旧规范保持不变")
            candidate.replace(target)
            try:
                self.refresh(force=True)
                self.prepare_index()
            except Exception:
                if previous is None:
                    target.unlink(missing_ok=True)
                else:
                    candidate.write_bytes(previous)
                    candidate.replace(target)
                self.refresh(force=True)
                self.prepare_index()
                raise
        return sum(c.source_file == filename for c in self.chunks)

    @_locked
    def delete_document(self, filename: str) -> None:
        if Path(filename).name != filename:
            raise ValueError("文件名无效")
        (self.kb_dir / filename).unlink()
        self.refresh(force=True)
        self.prepare_index()

    def _current_fingerprint(self) -> tuple:
        if not self.kb_dir.is_dir():
            return ()
        return tuple(
            sorted(
                (p.name, p.stat().st_mtime_ns, p.stat().st_size)
                for p in self.kb_dir.iterdir()
                if p.suffix.lower() in {".md", ".txt", ".pdf", ".docx"} or p.name == "sources.json"
            )
        )

    @_locked
    def refresh(self, *, force: bool = False) -> bool:
        """目录有变化时重建索引；返回是否重建。"""
        fingerprint = self._current_fingerprint()
        if not force and fingerprint == self._fingerprint:
            return False
        self._fingerprint = fingerprint
        self.chunks = []
        self.sources = {}
        try:
            manifest = json.loads((self.kb_dir / "sources.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        if self.kb_dir.is_dir():
            for path in sorted(self.kb_dir.iterdir()):
                if path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}:
                    continue
                try:
                    text = _read_document(path)
                except Exception:
                    continue
                meta = manifest.get(path.name, {})
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if meta and meta.get("sha256") == digest:
                    self.sources[path.name] = {**meta, "provenance_status": "verified_checksum"}
                else:
                    self.sources[path.name] = {"provenance_status": "checksum_mismatch" if meta else "unverified", "sha256": digest}
                for index, (section, content) in enumerate(_split_clauses(text)):
                    self.chunks.append(
                        KnowledgeChunk(
                            chunk_id=f"KB-{path.stem}-{index:03d}",
                            source_file=path.name,
                            section=section[:80],
                            text=content,
                        )
                    )
        self._retriever = None  # 懒重建
        return True

    def _ensure_retriever(self):
        if self._retriever is None and self.chunks:
            documents = [c.text for c in self.chunks]
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer

                self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3))
                self._matrix = self._vectorizer.fit_transform(documents)
                self._retriever = "tfidf_char_ngram"
            except Exception:
                from site_safety.agents.text_similarity import PortableCharTfidf

                self._portable_vectorizer = PortableCharTfidf(documents)
                self._retriever = "portable_tfidf_char_ngram"
        return self._retriever

    @_locked
    def prepare_index(self) -> str:
        """Eagerly build the local index so the first detection is not delayed."""
        self.refresh()
        return self._ensure_retriever() or "empty"

    @_locked
    def search(
        self, query: str, *, top_k: int = 5, min_score: float = 0.10, allowed_sections=None, verified_only: bool = False
    ) -> List[dict]:
        self.refresh()
        if not query.strip() or self._ensure_retriever() is None:
            return []
        if self._retriever == "portable_tfidf_char_ngram":
            scores = self._portable_vectorizer.similarities(query)
        else:
            try:
                from sklearn.metrics.pairwise import cosine_similarity

                scores = cosine_similarity(
                    self._vectorizer.transform([query]), self._matrix
                )[0]
            except Exception:
                from site_safety.agents.text_similarity import PortableCharTfidf

                self._portable_vectorizer = PortableCharTfidf([c.text for c in self.chunks])
                self._retriever = "portable_tfidf_char_ngram"
                scores = self._portable_vectorizer.similarities(query)
        ranked = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)
        if allowed_sections is not None:
            ranked = [(c, s) for c, s in ranked if (c.source_file, c.section) in allowed_sections]
        if verified_only:
            ranked = [(c, s) for c, s in ranked if self.sources.get(c.source_file, {}).get("provenance_status") == "verified_checksum"]
        return [
            {
                "chunk_id": chunk.chunk_id,
                "source_file": chunk.source_file,
                "section": chunk.section,
                "text": chunk.text,
                **self._source_fields(chunk.source_file, chunk.section),
                "score": round(float(score), 4),
            }
            for chunk, score in ranked[:top_k]
            if score >= min_score
        ]

    @_locked
    def summary(self) -> dict:
        self.refresh()
        documents = []
        if self.kb_dir.is_dir():
            for path in sorted(self.kb_dir.iterdir()):
                if path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}:
                    continue
                documents.append(
                    {
                        "source_file": path.name,
                        **self._source_fields(path.name),
                        "size_bytes": path.stat().st_size,
                        "modified_at": path.stat().st_mtime,
                        "chunk_count": sum(c.source_file == path.name for c in self.chunks),
                    }
                )
        return {
            "files": [item["source_file"] for item in documents],
            "documents": documents,
            "file_count": len(documents),
            "chunk_count": len(self.chunks),
            "retriever": self._retriever or "not_built",
        }

    def _source_fields(self, filename, section=None):
        meta = self.sources.get(filename, {})
        fields = {k:v for k,v in meta.items() if k != "sections"}
        fields.update(meta.get("sections", {}).get(section, {}))
        fields["citation_status"] = "reference_only_not_violation_finding"
        return fields

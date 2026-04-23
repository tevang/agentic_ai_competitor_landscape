"""Chroma-backed storage and retrieval of normalized evidence documents."""

import chromadb

from lib.config import PathsConfig, RagConfig
from lib.models import EvidenceDoc
from lib.utils.text_utils import sha1_hash


class EvidenceStore:
    """Persist evidence snippets so later agents can retrieve prior findings via RAG."""

    def __init__(self, paths_config: PathsConfig, rag_config: RagConfig) -> None:
        """Create or open the configured Chroma collection."""

        self.paths_config = paths_config
        self.rag_config = rag_config
        self.client = chromadb.PersistentClient(path=paths_config.chroma_path)
        self.collection = self.client.get_or_create_collection(paths_config.chroma_collection_name)

    def add_docs(self, docs: list[EvidenceDoc]) -> None:
        """Upsert evidence documents into the configured Chroma collection."""

        if not docs:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []

        for doc in docs:
            ids.append(sha1_hash(f"{doc.phase}|{doc.step}|{doc.query}|{doc.url}"))
            documents.append((doc.text or doc.snippet or "")[: self.rag_config.chroma_document_char_limit])
            metadatas.append(
                {
                    "phase": doc.phase,
                    "step": doc.step,
                    "query": doc.query,
                    "url": doc.url,
                    "title": doc.title,
                }
            )

        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, text: str, n_results: int | None = None) -> list[dict[str, str]]:
        """Query the evidence store and return normalized evidence dictionaries."""

        try:
            count = self.collection.count()
        except Exception:
            count = 0

        if count == 0:
            return []

        query_count = min(n_results or self.rag_config.store_query_n_results, count)
        result = self.collection.query(query_texts=[text], n_results=query_count)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]

        output: list[dict[str, str]] = []
        for doc, meta in zip(docs, metas):
            output.append(
                {
                    "text": doc,
                    "phase": meta.get("phase", ""),
                    "step": meta.get("step", ""),
                    "query": meta.get("query", ""),
                    "url": meta.get("url", ""),
                    "title": meta.get("title", ""),
                }
            )

        return output
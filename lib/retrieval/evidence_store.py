"""Chroma-backed storage and retrieval of evidence, cached profiles, query plans, and verifications."""

import json
import time
from typing import Any

import chromadb

from lib.config import PathsConfig, RagConfig
from lib.models import Candidate, CompanyProfile, EvidenceDoc, VerificationResult
from lib.utils.text_utils import canonical_name, domain_from_url, sha1_hash


class EvidenceStore:
    """Persist evidence and structured outputs so later runs can reuse prior work."""

    def __init__(self, paths_config: PathsConfig, rag_config: RagConfig) -> None:
        """Create or open the configured Chroma collections."""

        self.paths_config = paths_config
        self.rag_config = rag_config
        self.client = chromadb.PersistentClient(path=paths_config.chroma_path)

        prefix = paths_config.chroma_collection_name
        self.evidence_collection = self.client.get_or_create_collection(f"{prefix}_evidence")
        self.profile_collection = self.client.get_or_create_collection(f"{prefix}_profiles")
        self.query_plan_collection = self.client.get_or_create_collection(f"{prefix}_query_plans")
        self.candidate_collection = self.client.get_or_create_collection(f"{prefix}_candidates")
        self.verification_collection = self.client.get_or_create_collection(f"{prefix}_verifications")

    def add_docs(self, docs: list[EvidenceDoc]) -> None:
        """Upsert evidence documents into the configured Chroma evidence collection."""

        if not docs:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        saved_at = time.time()

        for doc in docs:
            document_text = (doc.text or doc.snippet or "")[: self.rag_config.chroma_document_char_limit]
            content_hash = sha1_hash(document_text)
            doc_id = sha1_hash(
                f"evidence|{doc.phase}|{doc.step}|{doc.company_name}|{doc.query}|{doc.url}|{content_hash}"
            )
            ids.append(doc_id)
            documents.append(document_text)
            metadatas.append(
                {
                    "phase": doc.phase,
                    "step": doc.step,
                    "query": doc.query,
                    "url": doc.url,
                    "title": doc.title,
                    "snippet": doc.snippet[:500],
                    "company_name": doc.company_name,
                    "company_key": canonical_name(doc.company_name) if doc.company_name else "",
                    "source_type": doc.source_type,
                    "domain": domain_from_url(doc.url),
                    "saved_at": saved_at,
                }
            )

        self.evidence_collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, text: str, n_results: int | None = None) -> list[dict[str, str]]:
        """Query the evidence collection with vector similarity and return normalized dictionaries."""

        try:
            count = self.evidence_collection.count()
        except Exception:
            count = 0

        if count == 0:
            return []

        query_count = min(n_results or self.rag_config.store_query_n_results, count)
        result = self.evidence_collection.query(
            query_texts=[text],
            n_results=query_count,
            include=["documents", "metadatas"],
        )
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
                    "snippet": meta.get("snippet", ""),
                    "company_name": meta.get("company_name", ""),
                    "source_type": meta.get("source_type", ""),
                }
            )

        return output

    def get_step_evidence(self, phase: str, step: str, limit: int = 12) -> list[dict[str, str]]:
        """Return cached evidence docs for a pipeline step without vector ranking."""

        where = self._build_where([{"phase": phase}, {"step": step}])
        records = self._get_records(self.evidence_collection, where=where, limit=limit)
        return self._normalize_evidence_records(records)

    def get_company_evidence(self, company_name: str, limit: int = 10) -> list[dict[str, str]]:
        """Return cached evidence docs for a company without vector ranking."""

        where = {"company_key": canonical_name(company_name)}
        records = self._get_records(self.evidence_collection, where=where, limit=limit)
        return self._normalize_evidence_records(records)

    def get_url_evidence(self, url: str, limit: int = 3) -> list[dict[str, str]]:
        """Return cached evidence docs for a specific URL without vector ranking."""

        where = {"url": url}
        records = self._get_records(self.evidence_collection, where=where, limit=limit)
        return self._normalize_evidence_records(records)

    def save_query_plan(self, phase: str, step: str, queries: list[str]) -> None:
        """Persist a step-level query plan for later reuse."""

        saved_at = time.time()
        document = json.dumps({"queries": queries}, ensure_ascii=False)
        record_id = sha1_hash(f"query_plan|{phase}|{step}|{document}")
        self.query_plan_collection.upsert(
            ids=[record_id],
            documents=[document],
            metadatas=[{"phase": phase, "step": step, "saved_at": saved_at}],
        )

    def get_query_plan(self, phase: str, step: str) -> list[str]:
        """Return the most recent cached query plan for a pipeline step."""

        where = self._build_where([{"phase": phase}, {"step": step}])
        records = self._get_records(self.query_plan_collection, where=where, limit=5)
        for record in records:
            try:
                payload = json.loads(record["document"])
                return list(payload.get("queries", []))
            except Exception:
                continue
        return []

    def save_candidates(self, phase: str, step: str, candidates: list[Candidate]) -> None:
        """Persist extracted candidate lists for a pipeline step."""

        saved_at = time.time()
        document = json.dumps([candidate.model_dump() for candidate in candidates], ensure_ascii=False)
        record_id = sha1_hash(f"candidates|{phase}|{step}|{document}")
        self.candidate_collection.upsert(
            ids=[record_id],
            documents=[document],
            metadatas=[{"phase": phase, "step": step, "candidate_count": len(candidates), "saved_at": saved_at}],
        )

    def get_candidates(self, phase: str, step: str) -> list[Candidate]:
        """Return the most recent cached candidate list for a pipeline step."""

        where = self._build_where([{"phase": phase}, {"step": step}])
        records = self._get_records(self.candidate_collection, where=where, limit=5)
        for record in records:
            try:
                payload = json.loads(record["document"])
                return [Candidate(**item) for item in payload]
            except Exception:
                continue
        return []

    def save_company_profile(self, profile: CompanyProfile) -> None:
        """Persist a normalized company profile for later reuse."""

        saved_at = time.time()
        document = profile.model_dump_json()
        record_id = sha1_hash(f"profile|{canonical_name(profile.name)}|{document}")
        self.profile_collection.upsert(
            ids=[record_id],
            documents=[document],
            metadatas=[
                {
                    "company_key": canonical_name(profile.name),
                    "name": profile.name,
                    "confidence": profile.confidence,
                    "website": profile.website,
                    "saved_at": saved_at,
                }
            ],
        )

    def get_company_profile(self, company_name: str, min_confidence: float = 0.0) -> CompanyProfile | None:
        """Return the most recent confident cached company profile for a company."""

        where = {"company_key": canonical_name(company_name)}
        records = self._get_records(self.profile_collection, where=where, limit=10)
        for record in records:
            try:
                payload = json.loads(record["document"])
                profile = CompanyProfile(**payload)
                if profile.confidence >= min_confidence:
                    return profile
            except Exception:
                continue
        return None

    def save_verification(
        self,
        phase: str,
        step: str,
        company_name: str,
        candidate_rationale: str,
        verdict: VerificationResult,
    ) -> None:
        """Persist a step/company verification decision for later reuse."""

        saved_at = time.time()
        document = json.dumps(
            {
                "phase": phase,
                "step": step,
                "company_name": company_name,
                "candidate_rationale": candidate_rationale,
                "verdict": verdict.model_dump(),
            },
            ensure_ascii=False,
        )
        record_id = sha1_hash(f"verification|{phase}|{step}|{company_name}|{document}")
        self.verification_collection.upsert(
            ids=[record_id],
            documents=[document],
            metadatas=[
                {
                    "phase": phase,
                    "step": step,
                    "company_key": canonical_name(company_name),
                    "company_name": company_name,
                    "include": verdict.include,
                    "confidence": verdict.confidence,
                    "saved_at": saved_at,
                }
            ],
        )

    def get_verification(
        self,
        phase: str,
        step: str,
        company_name: str,
        min_confidence: float = 0.0,
    ) -> VerificationResult | None:
        """Return a cached verification decision for a company and step when confidence is high enough."""

        where = self._build_where(
            [{"phase": phase}, {"step": step}, {"company_key": canonical_name(company_name)}]
        )
        records = self._get_records(self.verification_collection, where=where, limit=10)
        for record in records:
            try:
                payload = json.loads(record["document"])
                verdict = VerificationResult(**payload["verdict"])
                if verdict.confidence >= min_confidence:
                    return verdict
            except Exception:
                continue
        return None

    def _get_records(
        self,
        collection,
        where: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get records from a Chroma collection using metadata filters and pagination limits."""

        kwargs: dict[str, Any] = {
            "limit": limit,
            "include": ["documents", "metadatas"],
        }
        if where:
            kwargs["where"] = where

        result = collection.get(**kwargs)
        ids = result.get("ids", [])
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []

        records: list[dict[str, Any]] = []
        for record_id, document, metadata in zip(ids, documents, metadatas):
            row = dict(metadata or {})
            row["id"] = record_id
            row["document"] = document or ""
            records.append(row)

        records.sort(key=lambda item: float(item.get("saved_at", 0.0)), reverse=True)
        return records

    def _build_where(self, filters: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Build a Chroma metadata filter using an AND clause when multiple fields are present."""

        valid_filters = [item for item in filters if item]
        if not valid_filters:
            return None
        if len(valid_filters) == 1:
            return valid_filters[0]
        return {"$and": valid_filters}

    def _normalize_evidence_records(self, records: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Normalize Chroma evidence rows into the structure expected by the rest of the pipeline."""

        normalized: list[dict[str, str]] = []
        for record in records:
            normalized.append(
                {
                    "text": record.get("document", ""),
                    "phase": record.get("phase", ""),
                    "step": record.get("step", ""),
                    "query": record.get("query", ""),
                    "url": record.get("url", ""),
                    "title": record.get("title", ""),
                    "snippet": record.get("snippet", ""),
                    "company_name": record.get("company_name", ""),
                    "source_type": record.get("source_type", ""),
                }
            )
        return normalized
import chromadb
from lib.models import EvidenceDoc
from lib.utils import sha1

class EvidenceStore:
    """
    A local vector store (ChromaDB) to cache and query evidence documents.
    """
    def __init__(self, path: str):
        """
        Initializes the ChromaDB client and collection.
        """
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection("evidence")

    def add_docs(self, docs: list[EvidenceDoc]):
        """
        Adds multiple evidence documents to the vector store.
        """
        if not docs:
            return
        
        ids = []
        metadatas = []
        documents = []
        
        for d in docs:
            # Use unique hash of URL + step as ID
            did = sha1(f"{d.url}:{d.step}")
            ids.append(did)
            metadatas.append({
                "phase": d.phase,
                "step": d.step,
                "query": d.query,
                "url": d.url,
                "title": d.title
            })
            # Combine snippet and text
            full_text = f"{d.title}\n{d.snippet}\n{d.text}"
            documents.append(full_text[:5000]) # Limit per doc for local chroma embedding

        self.collection.upsert(
            ids=ids,
            metadatas=metadatas,
            documents=documents
        )

    def query(self, text: str, n_results: int = 8) -> list[dict]:
        """
        Queries the vector store for documents similar to the given text.
        """
        results = self.collection.query(
            query_texts=[text],
            n_results=n_results
        )
        
        out = []
        if not results or not results["ids"]:
            return out
            
        for i in range(len(results["ids"][0])):
            out.append({
                "id": results["ids"][0][i],
                "metadata": results["metadatas"][0][i],
                "text": results["documents"][0][i],
                "distance": results["distances"][0][i] if "distances" in results else 0
            })
        return out

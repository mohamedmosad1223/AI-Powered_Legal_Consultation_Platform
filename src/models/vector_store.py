import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.http import models
from dotenv import load_dotenv

load_dotenv()

class VectorStore:
    def __init__(self, collection_name="legal_knowledge", vector_size=1024):
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.client = QdrantClient(url=qdrant_url)
        self.collection_name = collection_name
        self.vector_size = vector_size
        
        self._init_collection()

    def _init_collection(self):
        """Creates the collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE
                ),
            )
            print(f"Created Qdrant collection: {self.collection_name}")

    def upsert_points(self, ids: list[str], embeddings: list[list[float]], payloads: list[dict]):
        """
        Inserts or updates points in the collection.
        ids must be list of UUID strings or integers.
        """
        # Convert string IDs (from Neo4j) to UUIDs for Qdrant if they aren't already valid UUIDs
        qdrant_ids = []
        for id_str in ids:
            try:
                qdrant_ids.append(str(uuid.UUID(id_str)))
            except ValueError:
                # Generate a deterministic UUID based on the string ID
                qdrant_ids.append(str(uuid.uuid5(uuid.NAMESPACE_OID, id_str)))

        points = [
            models.PointStruct(
                id=q_id,
                vector=emb,
                payload=payload
            )
            for q_id, emb, payload in zip(qdrant_ids, embeddings, payloads)
        ]
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def search(self, query_embedding: list[float], limit: int = 5, filter_dict: dict = None) -> list[dict]:
        """
        Searches for the closest vectors.
        filter_dict can be used to filter by metadata (e.g., {"node_type": "ArticleVersion"}).
        Returns a list of dicts with 'id', 'score', and 'payload'.
        """
        qdrant_filter = None
        if filter_dict:
            must_conditions = []
            for key, value in filter_dict.items():
                must_conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value)
                    )
                )
            qdrant_filter = models.Filter(must=must_conditions)

        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=limit,
            query_filter=qdrant_filter
        )
        
        results = []
        for hit in search_result.points:
            results.append({
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload
            })
            
        return results

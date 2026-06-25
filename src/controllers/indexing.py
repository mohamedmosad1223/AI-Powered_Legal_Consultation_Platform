import sys
import os

# Reconfigure stdout for Arabic characters on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.models.neo4j_model import Neo4jModel
from src.models.embeddings_model import EmbeddingsModel
from src.models.vector_store import VectorStore

class IndexingController:
    def __init__(self):
        self.neo4j = Neo4jModel()
        self.embedder = EmbeddingsModel()
        self.vector_store = VectorStore()

    def run_indexing(self):
        """
        Reads ArticleVersions and Judgments from Neo4j,
        embeds them using Cohere, and stores them in Qdrant.
        """
        if not self.embedder.client:
            print("Cannot run indexing: Cohere API Key is missing.")
            return

        print("Starting indexing process...")
        
        # 1. Index Article Versions
        print("Fetching ArticleVersions from Neo4j...")
        articles = []
        with self.neo4j.driver.session() as session:
            result = session.run("MATCH (av:ArticleVersion) RETURN av")
            for record in result:
                av = record["av"]
                props = dict(av)
                if "text" in props and props["text"].strip():
                    articles.append({
                        "id": props["version_id"],
                        "text": f"المادة {props.get('number', '')}:\n{props['text']}",
                        "type": "ArticleVersion",
                        "metadata": {
                            "law_version_id": props.get("law_version_id", ""),
                            "number": props.get("number", "")
                        }
                    })

        self._batch_index(articles, "ArticleVersions")

        # 2. Index Judgments
        print("Fetching Judgments from Neo4j...")
        judgments = []
        with self.neo4j.driver.session() as session:
            result = session.run("MATCH (j:Judgment) RETURN j")
            for record in result:
                j = record["j"]
                props = dict(j)
                if "full_text" in props and props["full_text"].strip():
                    judgments.append({
                        "id": props["ruling_id"],
                        "text": f"حكم رقم {props.get('case_number', '')} المحكمة {props.get('court', '')}:\n{props['full_text'][:2000]}...", # Truncate long judgments for embedding
                        "type": "Judgment",
                        "metadata": {
                            "case_number": props.get("case_number", ""),
                            "court": props.get("court", ""),
                            "date": props.get("date", "")
                        }
                    })

        self._batch_index(judgments, "Judgments")
        print("Indexing completed successfully!")

    def _batch_index(self, items: list[dict], name: str, batch_size: int = 50):
        if not items:
            print(f"No {name} found to index.")
            return

        print(f"Indexing {len(items)} {name}...")
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            texts = [item["text"] for item in batch]
            ids = [item["id"] for item in batch]
            payloads = [
                {
                    "node_type": item["type"],
                    "source_id": item["id"],
                    "text": item["text"],
                    "metadata": item["metadata"]
                }
                for item in batch
            ]

            try:
                # Embed texts
                embeddings = self.embedder.embed_texts(texts, input_type="search_document")
                
                # Upsert to Qdrant
                self.vector_store.upsert_points(ids=ids, embeddings=embeddings, payloads=payloads)
                print(f"  Indexed batch {i//batch_size + 1} ({len(batch)} items) for {name}")
            except Exception as e:
                print(f"  Error indexing batch: {e}")

if __name__ == "__main__":
    controller = IndexingController()
    controller.run_indexing()

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
        Reads Paragraphs, Items and Judgments from Neo4j,
        embeds them using Cohere, and stores them in Qdrant.
        """
        if not self.embedder.client:
            print("Cannot run indexing: Cohere API Key is missing.")
            return

        print("Starting indexing process...")
        
        # 1. Index Paragraphs
        print("Fetching Paragraphs from Neo4j...")
        paragraphs = []
        with self.neo4j.driver.session() as session:
            result = session.run(
                """
                MATCH (av:ArticleVersion)-[:HAS_PARAGRAPH]->(p:Paragraph)
                OPTIONAL MATCH (p)-[:HAS_ITEM]->(i:Item)
                WITH p, av.number AS art_num, i
                ORDER BY i.number
                RETURN p, art_num, collect(i) AS items
                """
            )
            for record in result:
                p = record["p"]
                art_num = record["art_num"]
                items = [item for item in record["items"] if item is not None]
                props = dict(p)
                p_text = props.get("text", "").strip()
                p_letter = props.get("letter", "")
                
                # Append items if they exist
                if items:
                    items_list = []
                    for item in items:
                        item_props = dict(item)
                        item_num = item_props.get("number")
                        item_text = item_props.get("text", "").strip()
                        if item_text:
                            items_list.append(f"{item_num}- {item_text}")
                    if items_list:
                        p_text += "\n" + "\n".join(items_list)
                
                if p_text:
                    if p_letter == "عام":
                        text_to_embed = f"المادة {art_num}:\n{p_text}"
                    else:
                        text_to_embed = f"المادة {art_num} فقرة {p_letter}:\n{p_text}"
                        
                    paragraphs.append({
                        "id": props["paragraph_id"],
                        "text": text_to_embed,
                        "type": "Paragraph",
                        "metadata": {
                            "article_number": art_num,
                            "letter": p_letter
                        }
                    })

        self._batch_index(paragraphs, "Paragraphs")

        # 2. Index Items
        print("Fetching Items from Neo4j...")
        items = []
        with self.neo4j.driver.session() as session:
            result = session.run(
                """
                MATCH (av:ArticleVersion)-[:HAS_PARAGRAPH]->(p:Paragraph)-[:HAS_ITEM]->(i:Item)
                RETURN i, p.letter AS para_letter, av.number AS art_num
                """
            )
            for record in result:
                i = record["i"]
                para_letter = record["para_letter"]
                art_num = record["art_num"]
                props = dict(i)
                i_text = props.get("text", "").strip()
                i_num = props.get("number")
                
                if i_text:
                    if para_letter == "عام":
                        text_to_embed = f"المادة {art_num} بند {i_num}:\n{i_text}"
                    else:
                        text_to_embed = f"المادة {art_num} فقرة {para_letter} بند {i_num}:\n{i_text}"
                        
                    items.append({
                        "id": props["item_id"],
                        "text": text_to_embed,
                        "type": "Item",
                        "metadata": {
                            "article_number": art_num,
                            "paragraph_letter": para_letter,
                            "number": i_num
                        }
                    })

        self._batch_index(items, "Items")

        # 3. Index Judgments
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

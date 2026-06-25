from typing import Optional, Union
import difflib
import re
from src.models.embeddings_model import EmbeddingsModel
from src.models.vector_store import VectorStore
from src.models.llm_client import LLMClient
from src.models.neo4j_model import Neo4jModel

# Version display labels
VERSION_LABELS = {
    "2015":    "نسخة 2015 (الأصلية)",
    "amended": "النسخة المعدّلة (الأحدث)",
}

CHANGE_TYPES = {
    "unchanged": "بدون تغيير",
    "modified":  "معدّلة",
    "added":     "مضافة",
    "deleted":   "محذوفة",
}

class RAGController:
    def __init__(self):
        self.embedder = EmbeddingsModel()
        self.vector_store = VectorStore()
        self.llm = LLMClient()
        self.neo4j = Neo4jModel()

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────

    @staticmethod
    def _parse_source_id(source_id: str) -> dict:
        """
        Parses a source_id like 'law_34_2014_art_5_v_2015'
        Returns dict with law_id, article_number, version_name.
        """
        m = re.match(
            r"(?P<law_id>law_\d+_\d+)_art_(?P<art_num>\d+)_v_(?P<version>.+)",
            source_id
        )
        if m:
            return {
                "law_id": m.group("law_id"),
                "article_number": int(m.group("art_num")),
                "version_name": m.group("version"),
            }
        return {}

    def _compare_versions(self, text_2015: str, text_amended: str) -> dict:
        """
        Compares two article version texts and returns:
        - change_type: unchanged / modified / added / deleted
        - diff_summary: human-readable Arabic description of what changed
        - diff_lines: list of diff lines for display
        """
        if not text_2015 and text_amended:
            return {
                "change_type": "added",
                "diff_summary": "هذه المادة مضافة في النسخة المعدّلة ولم تكن موجودة في نسخة 2015.",
                "diff_lines": []
            }
        if text_2015 and not text_amended:
            return {
                "change_type": "deleted",
                "diff_summary": "هذه المادة كانت موجودة في نسخة 2015 وتم حذفها في النسخة المعدّلة.",
                "diff_lines": []
            }

        lines_2015    = text_2015.splitlines(keepends=True)
        lines_amended = text_amended.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            lines_2015,
            lines_amended,
            fromfile="نسخة 2015",
            tofile="النسخة المعدّلة",
            lineterm=""
        ))

        if not diff:
            return {
                "change_type": "unchanged",
                "diff_summary": "لا يوجد فرق بين النسختين، النص متطابق.",
                "diff_lines": []
            }

        added_lines   = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
        removed_lines = [l for l in diff if l.startswith("-") and not l.startswith("---")]

        parts = []
        if removed_lines:
            parts.append(f"تم حذف {len(removed_lines)} سطر/أسطر")
        if added_lines:
            parts.append(f"تمت إضافة {len(added_lines)} سطر/أسطر")

        diff_summary = "التغييرات: " + " و".join(parts) + " بين النسخة الأصلية (2015) والنسخة المعدّلة."

        return {
            "change_type": "modified",
            "diff_summary": diff_summary,
            "diff_lines": diff
        }

    def _get_version_info_for_article(self, source_id: str) -> Optional[dict]:
        """
        Given a source_id (ArticleVersion), fetches both versions from Neo4j
        and returns a full comparison object.
        """
        parsed = self._parse_source_id(source_id)
        if not parsed:
            return None

        law_id  = parsed["law_id"]
        art_num = parsed["article_number"]

        all_versions = self.neo4j.get_all_versions_of_article(law_id, art_num)
        if not all_versions:
            return None

        by_version = {v["version_name"]: v for v in all_versions}
        text_2015    = by_version.get("2015",    {}).get("text", "")
        text_amended = by_version.get("amended", {}).get("text", "")

        comparison = self._compare_versions(text_2015, text_amended)

        # Determine which is the "active" (latest) version
        latest_version = "amended" if "amended" in by_version else "2015"

        return {
            "article_number": art_num,
            "law_id": law_id,
            "latest_version": latest_version,
            "latest_version_label": VERSION_LABELS.get(latest_version, latest_version),
            "change_type": comparison["change_type"],
            "change_type_label": CHANGE_TYPES.get(comparison["change_type"], comparison["change_type"]),
            "diff_summary": comparison["diff_summary"],
            "text_2015": text_2015,
            "text_amended": text_amended,
            "versions_available": list(by_version.keys()),
        }

    # ──────────────────────────────────────────────
    # MAIN PIPELINE
    # ──────────────────────────────────────────────

    def query(self, user_question: str) -> dict:
        """
        Main RAG pipeline:
        1. Embed user query.
        2. Retrieve relevant docs from Qdrant.
        3. Enhance with Neo4j graph traversal + version comparison.
        4. Generate response with Groq LLM.
        """
        print("\n" + "="*50)
        print(f"[الخطوة 1] استلام السؤال: {user_question}")

        if not self.embedder.client or not self.llm.client:
            print("[خطأ] مفاتيح API غير معدة.")
            return {
                "answer": "عذراً، النظام غير معد بالكامل. يرجى التأكد من إعداد مفاتيح API لـ Cohere و Groq.",
                "sources": []
            }

        # 1. Embed Query
        print("[الخطوة 2] جاري تحويل السؤال إلى متجهات (Embedding) باستخدام Cohere...")
        try:
            query_emb = self.embedder.embed_query(user_question)
            print(f"✅ تم التحويل بنجاح. (حجم المتجه: {len(query_emb)} بُعد)")
        except Exception as e:
            print(f"❌ خطأ في التحويل: {str(e)}")
            return {"answer": f"خطأ في تحليل السؤال: {str(e)}", "sources": []}

        # 2. Retrieve from Qdrant
        print("[الخطوة 3] جاري البحث في قاعدة البيانات المتجهة (Qdrant) عن أقرب النصوص...")
        try:
            search_results = self.vector_store.search(query_emb, limit=5)
            print(f"✅ تم العثور على {len(search_results)} نتيجة من Qdrant.")
        except Exception as e:
            print(f"❌ خطأ في البحث: {str(e)}")
            return {"answer": f"خطأ في البحث عن المعلومات: {str(e)}", "sources": []}

        if not search_results:
            print("⚠ لم يتم العثور على أي نتائج مطابقة.")
            return {
                "answer": "لم أتمكن من العثور على أي معلومات قانونية متعلقة بسؤالك.",
                "sources": []
            }

        # 3. Pack Context + Version Comparison + Judgments
        print("[الخطوة 4] جاري تجهيز السياق ومقارنة الإصدارات وجمع الأحكام...")
        context_docs      = []
        source_references = []
        all_judgments     = []          # separate list of judgment cards for the UI
        seen_rulings: set[str] = set()  # avoid duplicates

        # Track articles we've already done comparison for (avoid duplicates)
        compared_articles: set[tuple] = set()

        for idx, res in enumerate(search_results, 1):
            payload   = res["payload"]
            node_type = payload.get("node_type", "")
            source_id = payload.get("source_id", "")
            text      = payload.get("text", "")

            print(f"\n  - نتيجة #{idx}: [نوع: {node_type}] | [تطابق: {(res['score']*100):.1f}%] | [{source_id}]")

            version_info = None

            if node_type == "ArticleVersion":
                parsed = self._parse_source_id(source_id)
                art_key = (parsed.get("law_id", ""), parsed.get("article_number", 0))
                law_id  = parsed.get("law_id", "")
                art_num = parsed.get("article_number", 0)

                source_version = parsed.get("version_name", "")
                source_label = (
                    f"مادة {art_num} "
                    f"({VERSION_LABELS.get(source_version, source_version)})"
                )

                # Version comparison (once per article)
                if art_key not in compared_articles and law_id:
                    compared_articles.add(art_key)
                    print(f"    * جاري مقارنة إصدارات المادة {art_num}...")
                    version_info = self._get_version_info_for_article(source_id)
                    if version_info:
                        print(f"    * نوع التغيير: {version_info['change_type_label']} | أحدث نسخة: {version_info['latest_version_label']}")
                        # Use the latest version's text for LLM context
                        if version_info["latest_version"] == "amended" and version_info["text_amended"]:
                            text = version_info["text_amended"]
                        elif version_info["text_2015"]:
                            text = version_info["text_2015"]
                        text += f"\n\n[ملاحظة]: {version_info['diff_summary']}"

                    # ── Fetch full judgment details from Neo4j ──────────────
                    print(f"    * جاري جلب الأحكام المرتبطة بالمادة {art_num}...")
                    try:
                        raw_judgments = self.neo4j.get_judgments_for_article(law_id, art_num)
                        print(f"    * تم العثور على {len(raw_judgments)} حكم مرتبط.")
                        for j in raw_judgments:
                            rid = j.get("ruling_id", "")
                            if rid and rid not in seen_rulings:
                                seen_rulings.add(rid)
                                all_judgments.append(j)
                    except Exception as e:
                        print(f"    * تحذير في جلب الأحكام: {e}")

            elif node_type == "Judgment":
                source_label = f"حكم قضائي رقم {payload.get('metadata', {}).get('case_number', '')}"
            else:
                source_label = source_id

            context_docs.append({"source": source_label, "text": text})
            source_references.append({
                "id":           source_id,
                "type":         node_type,
                "label":        source_label,
                "score":        res["score"],
                "text":         text,
                "version_info": version_info,
            })

        # 4. Build LLM context — include judgment summaries
        judgments_context = ""
        if all_judgments:
            judgments_context = "\n\n## الأحكام القضائية المرتبطة:\n"
            for j in all_judgments:
                judgments_context += (
                    f"\n- **الحكم رقم {j.get('case_number','')}** "
                    f"({j.get('court','')}, {j.get('date','')})\n"
                    f"  النتيجة: {j.get('outcome','')}\n"
                    f"  الموضوع: {j.get('subject','')}\n"
                )
            # Add to the last context doc so LLM sees it
            if context_docs:
                context_docs[-1]["text"] += judgments_context

        # 5. Generate Answer & Evaluate Judgments
        # Limit to top 2 judgments to avoid token limit errors on free tier API
        all_judgments = all_judgments[:2]
        print(f"\n[الخطوة 5] إرسال {len(context_docs)} مصادر + {len(all_judgments)} حكم إلى Groq LLM...")
        
        filtered_judgments = []
        if all_judgments:
            try:
                response_data = self.llm.generate_rag_response(user_question, context_docs, all_judgments)
                answer = response_data.get("answer", "")
                
                # Match evaluations with judgments and filter relevant ones
                eval_dict = {}
                for item in response_data.get("judgments_relevance", []):
                    rid = item.get("ruling_id")
                    if rid:
                        eval_dict[str(rid).strip().upper()] = item
                
                for idx, j in enumerate(all_judgments, 1):
                    rid_key = f"J{idx}"
                    evaluation = eval_dict.get(rid_key)
                    if evaluation and evaluation.get("is_relevant", False):
                        j["relevance_explanation"] = evaluation.get("relevance_explanation", "")
                        filtered_judgments.append(j)
            except Exception as e:
                print(f"❌ خطأ في معالجة RAG الذكية للأحكام: {e}")
                # Fallback to normal response and all judgments if RAG analysis fails
                answer = self.llm.generate_response(user_question, context_docs)
                filtered_judgments = all_judgments
        else:
            answer = self.llm.generate_response(user_question, context_docs)
            
        print("✅ تم استلام الإجابة من Groq.")
        print("="*50 + "\n")

        return {
            "answer":    answer,
            "sources":   source_references,
            "judgments": filtered_judgments,
        }

    def _get_connected_judgments(self, article_version_id: str) -> str:
        """Legacy helper — short text summary of judgments (still used for version_info text)."""
        judgments_text = ""
        try:
            with self.neo4j.driver.session() as session:
                result = session.run(
                    """
                    MATCH (j:Judgment)-[:CITES]->(n)
                    WHERE (n:ArticleVersion AND n.version_id = $av_id)
                       OR (n:Paragraph AND n.paragraph_id STARTS WITH $prefix)
                    RETURN DISTINCT j.case_number AS case_num, j.outcome AS outcome
                    LIMIT 3
                    """,
                    av_id=article_version_id,
                    prefix=article_version_id + "_p_"
                )
                for rec in result:
                    judgments_text += f"- حكم رقم {rec['case_num']} (النتيجة: {rec['outcome']})\n"
        except Exception as e:
            print(f"Graph traversal warning: {e}")
        return judgments_text

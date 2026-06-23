import os
import re
import docx

class DocxParser:
    @staticmethod
    def parse_law(file_path):
        """
        Parses a Law docx file.
        Returns a dictionary representing the law structure:
        {
            "title": str,
            "law_number": int,
            "law_year": int,
            "articles": [
                {
                    "number": int,
                    "effective_date": str,
                    "text": str,
                    "paragraphs": [
                        {
                            "letter": str,
                            "text": str,
                            "items": [
                                {
                                    "number": int,
                                    "text": str
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        """
        doc = docx.Document(file_path)
        filename = os.path.basename(file_path)
        
        # Deduce title, number, year
        title = "قانون ضريبة الدخل"
        law_number = 34
        law_year = 2014
        
        articles = []
        current_article = None
        current_paragraph = None
        
        # We walk through paragraphs
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
                
            # Check if this paragraph indicates a new Article
            # Pattern examples: "المادة 1", "المادة 2   01-01-2015"
            art_match = re.match(r"^المادة\s+(\d+)(?:\s+([\d\-]+))?", text)
            if art_match:
                art_num = int(art_match.group(1))
                eff_date = art_match.group(2) if art_match.group(2) else "2015-01-01"
                
                current_article = {
                    "number": art_num,
                    "effective_date": eff_date,
                    "text": "",
                    "paragraphs": []
                }
                articles.append(current_article)
                current_paragraph = None
                continue
                
            if current_article is not None:
                # Add to total article raw text
                if current_article["text"]:
                    current_article["text"] += "\n" + text
                else:
                    current_article["text"] = text
                
                # ── Pattern 1: "أ-1-" or "أ- 1-" — paragraph letter + item on same line
                # Handles both "أ-1- نص" and "أ- 1- نص" (with optional space)
                combined_match = re.match(r"^([أ-ي])-\s*(\d+)-\s*(.*)", text)
                if combined_match:
                    letter    = combined_match.group(1)
                    item_num  = int(combined_match.group(2))
                    item_text = combined_match.group(3).strip()

                    current_paragraph = {
                        "letter": letter,
                        "text": item_text,
                        "items": [{"number": item_num, "text": item_text}]
                    }
                    current_article["paragraphs"].append(current_paragraph)
                    continue

                # ── Pattern 2: "أ- نص" — standalone paragraph (must NOT be followed by digit+dash)
                para_match = re.match(r"^([أ-ي])-(?!\d+-)\s*(.*)", text)
                if para_match:
                    letter = para_match.group(1)
                    para_text = para_match.group(2)
                    
                    current_paragraph = {
                        "letter": letter,
                        "text": para_text,
                        "items": []
                    }
                    current_article["paragraphs"].append(current_paragraph)
                    continue
                
                # Pattern 3: "1- text" (Standalone item under current paragraph)
                item_match = re.match(r"^(\d+)-\s*(.*)", text)
                if item_match and current_paragraph is not None:
                    item_num = int(item_match.group(1))
                    item_text = item_match.group(2)
                    
                    current_paragraph["items"].append({
                        "number": item_num,
                        "text": item_text
                    })
                    continue
                    
                # If it's plain text and we don't have a paragraph yet, make a default paragraph
                if not current_article["paragraphs"]:
                    default_para = {
                        "letter": "عام",
                        "text": text,
                        "items": []
                    }
                    current_article["paragraphs"].append(default_para)
                    current_paragraph = default_para
                else:
                    # Append to current paragraph text
                    if current_paragraph:
                        current_paragraph["text"] += "\n" + text
        
        return {
            "title": title,
            "law_number": law_number,
            "law_year": law_year,
            "articles": articles
        }

    @staticmethod
    def parse_judgment(file_path):
        """
        Parses a Judgment docx file.
        Returns a dictionary representing the judgment structure:
        {
            "ruling_id": str,
            "case_number": str,
            "court": str,
            "date": str,
            "title": str,
            "full_text": str,
            "citations": [
                {
                    "law_number": int,
                    "law_year": int,
                    "article_number": int,
                    "paragraph_letter": str
                }
            ]
        }
        """
        doc = docx.Document(file_path)
        filename = os.path.basename(file_path)
        
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        
        # Deduce metadata from first few paragraphs
        ruling_id = filename.replace(".docx", "")
        case_number = ""
        court = "المحكمة الضريبية"
        date = ""
        
        # Simple extraction heuristics
        for p in doc.paragraphs[:10]:
            t = p.text.strip()
            # Case number
            case_match = re.search(r"رقم (?:الدعوى|القضية):\s*([\d\s/]+)", t)
            if case_match:
                case_number = case_match.group(1).strip()
            # Court
            if "المحكمة الإدارية العليا" in t:
                court = "المحكمة الإدارية العليا"
            elif "محكمة التمييز" in t:
                court = "محكمة التمييز الأردنية"
            elif "محكمة البداية الضريبية" in t or "البداية الضريبية" in t:
                court = "محكمة البداية الضريبية"
            # Date
            date_match = re.search(r"تاريخ الفصل:\s*([\d\-]+)", t)
            if date_match:
                date = date_match.group(1).strip()
                
        if not case_number:
            # Fallback extract from filename
            num_match = re.search(r"رقم\s+(\d+)\s+لسنة\s+(\d+)", filename)
            if num_match:
                case_number = f"{num_match.group(1)}/{num_match.group(2)}"
        
        # Extract citations
        # We look for "المادة [number]" optionally followed by a paragraph letter or "من قانون ضريبة الدخل"
        citations = []
        
        # Look for "المادة (70/أ)" or "المادة 70 / أ" or "المادة 70 من قانون ضريبة الدخل"
        pattern = r"المادة\s*\(?(\d+)(?:\s*/?\s*([أ-ي]))?\)?(?:\s+من\s+قانون\s+ضريبة\s+الدخل)?"
        matches = re.finditer(pattern, full_text)
        for m in matches:
            art_num = int(m.group(1))
            letter = m.group(2) if m.group(2) else None
            citations.append({
                "law_number": 34,
                "law_year": 2014,
                "article_number": art_num,
                "paragraph_letter": letter
            })
            
        # De-duplicate citations
        unique_citations = []
        seen = set()
        for c in citations:
            key = (c["law_number"], c["law_year"], c["article_number"], c["paragraph_letter"])
            if key not in seen:
                seen.add(key)
                unique_citations.append(c)

        return {
            "ruling_id": ruling_id,
            "case_number": case_number if case_number else ruling_id,
            "court": court,
            "date": date if date else "2024-01-01",
            "title": ruling_id,
            "full_text": full_text,
            "citations": unique_citations
        }

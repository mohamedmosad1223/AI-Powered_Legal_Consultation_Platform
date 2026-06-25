from neo4j import GraphDatabase


class Neo4jModel:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password123"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def init_db(self):
        """
        Creates constraints and indexes.
        New schema:
          Law -> HAS_VERSION -> LawVersion -> HAS_ARTICLE -> ArticleVersion
               -> HAS_PARAGRAPH -> Paragraph -> HAS_ITEM -> Item
          Judgment -[:CITES]-> ArticleVersion | Paragraph
        """
        queries = [
            "CREATE CONSTRAINT law_id_unique IF NOT EXISTS FOR (l:Law) REQUIRE l.law_id IS UNIQUE",
            "CREATE CONSTRAINT law_version_id_unique IF NOT EXISTS FOR (lv:LawVersion) REQUIRE lv.version_id IS UNIQUE",
            "CREATE CONSTRAINT article_version_id_unique IF NOT EXISTS FOR (av:ArticleVersion) REQUIRE av.version_id IS UNIQUE",
            "CREATE CONSTRAINT paragraph_id_unique IF NOT EXISTS FOR (p:Paragraph) REQUIRE p.paragraph_id IS UNIQUE",
            "CREATE CONSTRAINT item_id_unique IF NOT EXISTS FOR (i:Item) REQUIRE i.item_id IS UNIQUE",
            "CREATE CONSTRAINT judgment_id_unique IF NOT EXISTS FOR (j:Judgment) REQUIRE j.ruling_id IS UNIQUE",
        ]
        with self.driver.session() as session:
            for query in queries:
                try:
                    session.run(query)
                except Exception as e:
                    print(f"Constraint warning: {e}")

    # ──────────────────────────────────────────────
    # INGESTION
    # ──────────────────────────────────────────────

    def insert_law(self, law_data, version_name="2015"):
        """
        Inserts law structure using the new hierarchy:
          Law -> LawVersion -> ArticleVersion -> Paragraph -> Item
        """
        law_id = f"law_{law_data['law_number']}_{law_data['law_year']}"
        law_version_id = f"{law_id}_v_{version_name}"
        effective_from = "01-01-2015" if version_name == "2015" else "بعد التعديلات"

        with self.driver.session() as session:
            # 1. Law node
            session.run(
                """
                MERGE (l:Law {law_id: $law_id})
                ON CREATE SET l.title = $title, l.number = $number, l.year = $year
                """,
                law_id=law_id,
                title=law_data["title"],
                number=law_data["law_number"],
                year=law_data["law_year"],
            )

            # 2. LawVersion node
            session.run(
                """
                MERGE (lv:LawVersion {version_id: $version_id})
                ON CREATE SET lv.version_name = $version_name,
                              lv.effective_from = $effective_from,
                              lv.law_id = $law_id
                """,
                version_id=law_version_id,
                version_name=version_name,
                effective_from=effective_from,
                law_id=law_id,
            )

            # 3. Law -[HAS_VERSION]-> LawVersion
            session.run(
                """
                MATCH (l:Law {law_id: $law_id})
                MATCH (lv:LawVersion {version_id: $version_id})
                MERGE (l)-[:HAS_VERSION]->(lv)
                """,
                law_id=law_id,
                version_id=law_version_id,
            )

            for art in law_data["articles"]:
                av_id = f"{law_id}_art_{art['number']}_v_{version_name}"

                # 4. ArticleVersion node (replaces old Article + ArticleVersion split)
                session.run(
                    """
                    MERGE (av:ArticleVersion {version_id: $av_id})
                    SET av.text           = $text,
                        av.effective_from = $effective_from,
                        av.status         = 'active',
                        av.number         = $number,
                        av.law_version_id = $law_version_id
                    """,
                    av_id=av_id,
                    text=art["text"],
                    effective_from=art["effective_date"],
                    number=art["number"],
                    law_version_id=law_version_id,
                )

                # 5. LawVersion -[HAS_ARTICLE]-> ArticleVersion
                session.run(
                    """
                    MATCH (lv:LawVersion {version_id: $lv_id})
                    MATCH (av:ArticleVersion {version_id: $av_id})
                    MERGE (lv)-[:HAS_ARTICLE]->(av)
                    """,
                    lv_id=law_version_id,
                    av_id=av_id,
                )

                # 6. Link amended version to 2015 version
                if version_name != "2015":
                    prev_av_id = f"{law_id}_art_{art['number']}_v_2015"
                    session.run(
                        """
                        MATCH (av:ArticleVersion {version_id: $av_id})
                        MATCH (prev:ArticleVersion {version_id: $prev_av_id})
                        MERGE (av)-[:REPLACES_VERSION]->(prev)
                        """,
                        av_id=av_id,
                        prev_av_id=prev_av_id,
                    )

                # 7. Paragraphs
                for para in art["paragraphs"]:
                    para_id = f"{av_id}_p_{para['letter']}"
                    session.run(
                        """
                        MERGE (p:Paragraph {paragraph_id: $para_id})
                        SET p.letter = $letter, p.text = $text,
                            p.article_version_id = $av_id
                        """,
                        para_id=para_id,
                        letter=para["letter"],
                        text=para["text"],
                        av_id=av_id,
                    )

                    session.run(
                        """
                        MATCH (av:ArticleVersion {version_id: $av_id})
                        MATCH (p:Paragraph {paragraph_id: $para_id})
                        MERGE (av)-[:HAS_PARAGRAPH]->(p)
                        """,
                        av_id=av_id,
                        para_id=para_id,
                    )

                    # 8. Items
                    for item in para["items"]:
                        item_id = f"{para_id}_i_{item['number']}"
                        session.run(
                            """
                            MERGE (i:Item {item_id: $item_id})
                            SET i.number = $number, i.text = $text
                            """,
                            item_id=item_id,
                            number=item["number"],
                            text=item["text"],
                        )
                        session.run(
                            """
                            MATCH (p:Paragraph {paragraph_id: $para_id})
                            MATCH (i:Item {item_id: $item_id})
                            MERGE (p)-[:HAS_ITEM]->(i)
                            """,
                            para_id=para_id,
                            item_id=item_id,
                        )

    def insert_judgment(self, judgment_data):
        """
        Inserts a Judgment node and creates CITES edges to the
        most-specific node available: Item > Paragraph > ArticleVersion.
        """
        with self.driver.session() as session:
            # ── Judgment node ─────────────────────────────────────────────
            session.run(
                """
                MERGE (j:Judgment {ruling_id: $ruling_id})
                SET j.case_number    = $case_number,
                    j.ruling_number  = $ruling_number,
                    j.ruling_year    = $ruling_year,
                    j.court          = $court,
                    j.court_type     = $court_type,
                    j.date           = $date,
                    j.outcome        = $outcome,
                    j.subject        = $subject,
                    j.title          = $title,
                    j.full_text      = $full_text
                """,
                ruling_id=judgment_data["ruling_id"],
                case_number=judgment_data["case_number"],
                ruling_number=judgment_data.get("ruling_number", 0),
                ruling_year=judgment_data.get("ruling_year", 0),
                court=judgment_data["court"],
                court_type=judgment_data.get("court_type", "tax_first"),
                date=judgment_data["date"],
                outcome=judgment_data.get("outcome", ""),
                subject=judgment_data.get("subject", ""),
                title=judgment_data["title"],
                full_text=judgment_data["full_text"],
            )

            for cit in judgment_data["citations"]:
                law_num  = cit["law_number"]
                law_yr   = cit["law_year"]
                art_num  = cit["article_number"]
                para_ltr = cit.get("paragraph_letter")
                item_num = cit.get("item_number")
                cit_txt  = cit.get("citation_text", "")

                law_id = f"law_{law_num}_{law_yr}"

                # CITES properties (stored on the edge)
                edge_props = {
                    "ruling_id":         judgment_data["ruling_id"],
                    "citation_text":     cit_txt,
                    "paragraph_letter":  para_ltr,
                    "item_number":       item_num,
                    "law_name":          cit.get("law_name", ""),
                }

                if para_ltr and item_num is not None:
                    # ── Most specific: link to Item ───────────────────────
                    for v in ("amended", "2015"):
                        item_id = f"{law_id}_art_{art_num}_v_{v}_p_{para_ltr}_i_{item_num}"
                        session.run(
                            """
                            MATCH (j:Judgment {ruling_id: $ruling_id})
                            MATCH (i:Item {item_id: $item_id})
                            MERGE (j)-[r:CITES]->(i)
                            SET r.citation_text    = $citation_text,
                                r.paragraph_letter = $paragraph_letter,
                                r.item_number      = $item_number,
                                r.law_name         = $law_name
                            """,
                            ruling_id=edge_props["ruling_id"],
                            item_id=item_id,
                            citation_text=cit_txt,
                            paragraph_letter=para_ltr,
                            item_number=item_num,
                            law_name=edge_props["law_name"],
                        )

                elif para_ltr:
                    # ── Medium: link to Paragraph ─────────────────────────
                    for v in ("amended", "2015"):
                        para_id = f"{law_id}_art_{art_num}_v_{v}_p_{para_ltr}"
                        session.run(
                            """
                            MATCH (j:Judgment {ruling_id: $ruling_id})
                            MATCH (p:Paragraph {paragraph_id: $para_id})
                            MERGE (j)-[r:CITES]->(p)
                            SET r.citation_text    = $citation_text,
                                r.paragraph_letter = $paragraph_letter,
                                r.law_name         = $law_name
                            """,
                            ruling_id=edge_props["ruling_id"],
                            para_id=para_id,
                            citation_text=cit_txt,
                            paragraph_letter=para_ltr,
                            law_name=edge_props["law_name"],
                        )

                else:
                    # ── Least specific: link to ArticleVersion ────────────
                    for v in ("amended", "2015"):
                        av_id = f"{law_id}_art_{art_num}_v_{v}"
                        session.run(
                            """
                            MATCH (j:Judgment {ruling_id: $ruling_id})
                            MATCH (av:ArticleVersion {version_id: $av_id})
                            MERGE (j)-[r:CITES]->(av)
                            SET r.citation_text = $citation_text,
                                r.law_name      = $law_name
                            """,
                            ruling_id=edge_props["ruling_id"],
                            av_id=av_id,
                            citation_text=cit_txt,
                            law_name=edge_props["law_name"],
                        )

    # ──────────────────────────────────────────────
    # LAZY-LOADING TREE QUERIES
    # ──────────────────────────────────────────────

    def get_law_nodes(self):
        """Returns only Law nodes — the root of the tree."""
        nodes = []
        with self.driver.session() as session:
            result = session.run("MATCH (l:Law) RETURN l ORDER BY l.year")
            for record in result:
                l = record["l"]
                props = dict(l)
                law_id = props.get("law_id", "")
                nodes.append({
                    "data": {
                        "id": law_id,
                        "label": f"قانون {props.get('number')} لسنة {props.get('year')}",
                        "type": "Law",
                        "hasChildren": True,
                        "properties": props,
                    }
                })
        return {"nodes": nodes, "edges": []}

    def get_children(self, node_id: str, node_type: str):
        """
        Returns direct children nodes + edges for expand-on-click tree.
        Levels:
          Law          -> LawVersion (HAS_VERSION)
          LawVersion   -> ArticleVersion (HAS_ARTICLE)
          ArticleVersion -> Paragraph (HAS_PARAGRAPH) + Judgment (CITES)
          Paragraph    -> Item (HAS_ITEM) + Judgment (CITES)
        """
        nodes = []
        edges = []

        with self.driver.session() as session:

            if node_type == "Law":
                result = session.run(
                    """
                    MATCH (l:Law {law_id: $node_id})-[:HAS_VERSION]->(lv:LawVersion)
                    RETURN lv ORDER BY lv.version_name
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    lv = rec["lv"]
                    props = dict(lv)
                    vid = props["version_id"]
                    vname = props.get("version_name", vid)
                    label = f"نسخة {vname}"
                    nodes.append({
                        "data": {
                            "id": vid,
                            "label": label,
                            "type": "LawVersion",
                            "hasChildren": True,
                            "properties": props,
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{node_id}__{vid}",
                            "source": node_id,
                            "target": vid,
                            "label": "HAS_VERSION",
                        }
                    })

            elif node_type == "LawVersion":
                result = session.run(
                    """
                    MATCH (lv:LawVersion {version_id: $node_id})-[:HAS_ARTICLE]->(av:ArticleVersion)
                    RETURN av ORDER BY av.number
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    av = rec["av"]
                    props = dict(av)
                    av_id = props["version_id"]
                    art_num = props.get("number", "?")
                    # Exclude heavy text from list view
                    light_props = {k: v for k, v in props.items() if k != "text"}
                    nodes.append({
                        "data": {
                            "id": av_id,
                            "label": f"مادة {art_num}",
                            "type": "ArticleVersion",
                            "hasChildren": True,
                            "properties": light_props,
                            "text": props.get("text", ""),
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{node_id}__{av_id}",
                            "source": node_id,
                            "target": av_id,
                            "label": "HAS_ARTICLE",
                        }
                    })

            elif node_type == "ArticleVersion":
                # Children: Paragraphs
                result = session.run(
                    """
                    MATCH (av:ArticleVersion {version_id: $node_id})-[:HAS_PARAGRAPH]->(p:Paragraph)
                    RETURN p ORDER BY p.letter
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    p = rec["p"]
                    props = dict(p)
                    pid = props["paragraph_id"]
                    nodes.append({
                        "data": {
                            "id": pid,
                            "label": f"فقرة {props.get('letter', '')}",
                            "type": "Paragraph",
                            "hasChildren": True,
                            "properties": props,
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{node_id}__{pid}",
                            "source": node_id,
                            "target": pid,
                            "label": "HAS_PARAGRAPH",
                        }
                    })

                # Children: Judgments citing this article directly
                result = session.run(
                    """
                    MATCH (j:Judgment)-[:CITES]->(av:ArticleVersion {version_id: $node_id})
                    RETURN j
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    j = rec["j"]
                    props = dict(j)
                    jid = props["ruling_id"]
                    light_props = {k: v for k, v in props.items() if k != "full_text"}
                    nodes.append({
                        "data": {
                            "id": jid,
                            "label": f"حكم {props.get('case_number', jid)}",
                            "type": "Judgment",
                            "hasChildren": False,
                            "properties": light_props,
                            "text": props.get("full_text", ""),
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{jid}__{node_id}",
                            "source": jid,
                            "target": node_id,
                            "label": "CITES",
                        }
                    })

            elif node_type == "Paragraph":
                # Children: Items
                result = session.run(
                    """
                    MATCH (p:Paragraph {paragraph_id: $node_id})-[:HAS_ITEM]->(i:Item)
                    RETURN i ORDER BY i.number
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    i = rec["i"]
                    props = dict(i)
                    iid = props["item_id"]
                    # Does this item have judgments citing it?
                    cnt = session.run(
                        "MATCH (j:Judgment)-[:CITES]->(i:Item {item_id: $iid}) RETURN count(j) AS c",
                        iid=iid,
                    ).single()["c"]
                    nodes.append({
                        "data": {
                            "id": iid,
                            "label": f"بند {props.get('number', '')}",
                            "type": "Item",
                            "hasChildren": cnt > 0,
                            "properties": props,
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{node_id}__{iid}",
                            "source": node_id,
                            "target": iid,
                            "label": "HAS_ITEM",
                        }
                    })

                # Judgments citing this paragraph directly
                result = session.run(
                    """
                    MATCH (j:Judgment)-[:CITES]->(p:Paragraph {paragraph_id: $node_id})
                    RETURN j
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    j = rec["j"]
                    props = dict(j)
                    jid = props["ruling_id"]
                    light_props = {k: v for k, v in props.items() if k != "full_text"}
                    nodes.append({
                        "data": {
                            "id": jid,
                            "label": f"حكم {props.get('case_number', jid)}",
                            "type": "Judgment",
                            "hasChildren": False,
                            "properties": light_props,
                            "text": props.get("full_text", ""),
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{jid}__{node_id}",
                            "source": jid,
                            "target": node_id,
                            "label": "CITES",
                        }
                    })

            elif node_type == "Item":
                # Judgments citing this specific item/bund
                result = session.run(
                    """
                    MATCH (j:Judgment)-[r:CITES]->(i:Item {item_id: $node_id})
                    RETURN j, r
                    """,
                    node_id=node_id,
                )
                for rec in result:
                    j    = rec["j"]
                    r    = rec["r"]
                    props = dict(j)
                    jid   = props["ruling_id"]
                    light_props = {k: v for k, v in props.items() if k != "full_text"}
                    nodes.append({
                        "data": {
                            "id": jid,
                            "label": f"حكم {props.get('case_number', jid)}",
                            "type": "Judgment",
                            "hasChildren": False,
                            "properties": light_props,
                            "text": props.get("full_text", ""),
                            "citation_text": dict(r).get("citation_text", ""),
                        }
                    })
                    edges.append({
                        "data": {
                            "id": f"e_{jid}__{node_id}",
                            "source": jid,
                            "target": node_id,
                            "label": "CITES",
                        }
                    })

        return {"nodes": nodes, "edges": edges}

    # ──────────────────────────────────────────────
    # UTILITIES
    # ──────────────────────────────────────────────

    def clear_db(self):
        """Wipes the database for clean ingestion."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    # ──────────────────────────────────────────────
    # VERSION COMPARISON
    # ──────────────────────────────────────────────

    def get_article_version(self, version_id: str) -> dict | None:
        """
        Returns a single ArticleVersion dict (id, number, text, version_name, law_version_id).
        Returns None if not found.
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (av:ArticleVersion {version_id: $vid}) RETURN av",
                vid=version_id
            ).single()
            if result:
                props = dict(result["av"])
                return props
        return None

    def get_judgments_for_article(self, law_id: str, article_number: int) -> list[dict]:
        """
        Returns all Judgment nodes (with full details) that CITES any node
        (ArticleVersion, Paragraph, or Item) belonging to the given article
        across both law versions (2015 and amended).

        Returns a list of dicts with keys:
          ruling_id, case_number, ruling_number, ruling_year,
          court, court_type, date, outcome, subject, title, full_text
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[:CITES]->(n)
                WHERE (
                    (n:ArticleVersion AND n.version_id STARTS WITH $prefix)
                    OR
                    (n:Paragraph AND n.paragraph_id STARTS WITH $prefix)
                    OR
                    (n:Item AND n.item_id STARTS WITH $prefix)
                )
                RETURN DISTINCT j
                ORDER BY j.ruling_year, j.ruling_number
                """,
                prefix=f"{law_id}_art_{article_number}_v_"
            )
            judgments = []
            for rec in result:
                props = dict(rec["j"])
                judgments.append(props)
        return judgments

    def get_all_versions_of_article(self, law_id: str, article_number: int) -> list[dict]:
        """
        Returns all ArticleVersion nodes for a given law and article number,
        across all versions (2015, amended, etc.).
        Each dict has: version_id, number, text, effective_from, law_version_id, version_name
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (lv:LawVersion)-[:HAS_ARTICLE]->(av:ArticleVersion)
                WHERE lv.law_id = $law_id AND av.number = $art_num
                RETURN av, lv.version_name AS ver_name
                ORDER BY lv.version_name
                """,
                law_id=law_id,
                art_num=article_number
            )
            versions = []
            for rec in result:
                props = dict(rec["av"])
                props["version_name"] = rec["ver_name"]
                versions.append(props)
        return versions


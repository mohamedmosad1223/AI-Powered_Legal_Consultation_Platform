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
        Inserts a Judgment node and links CITES relations
        to ArticleVersion (when no paragraph) or Paragraph.
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (j:Judgment {ruling_id: $ruling_id})
                SET j.case_number = $case_number,
                    j.court       = $court,
                    j.date        = $date,
                    j.title       = $title,
                    j.full_text   = $full_text
                """,
                ruling_id=judgment_data["ruling_id"],
                case_number=judgment_data["case_number"],
                court=judgment_data["court"],
                date=judgment_data["date"],
                title=judgment_data["title"],
                full_text=judgment_data["full_text"],
            )

            for cit in judgment_data["citations"]:
                law_id = f"law_{cit['law_number']}_{cit['law_year']}"

                if cit["paragraph_letter"]:
                    # Link to Paragraph (try amended first, fall back to 2015)
                    para_amended = f"{law_id}_art_{cit['article_number']}_v_amended_p_{cit['paragraph_letter']}"
                    para_2015 = f"{law_id}_art_{cit['article_number']}_v_2015_p_{cit['paragraph_letter']}"
                    session.run(
                        """
                        MATCH (j:Judgment {ruling_id: $ruling_id})
                        MATCH (p:Paragraph)
                        WHERE p.paragraph_id = $para_amended
                           OR p.paragraph_id = $para_2015
                        MERGE (j)-[:CITES]->(p)
                        """,
                        ruling_id=judgment_data["ruling_id"],
                        para_amended=para_amended,
                        para_2015=para_2015,
                    )
                else:
                    # Link to ArticleVersion (try amended first, fall back to 2015)
                    av_amended = f"{law_id}_art_{cit['article_number']}_v_amended"
                    av_2015 = f"{law_id}_art_{cit['article_number']}_v_2015"
                    session.run(
                        """
                        MATCH (j:Judgment {ruling_id: $ruling_id})
                        MATCH (av:ArticleVersion)
                        WHERE av.version_id = $av_amended
                           OR av.version_id = $av_2015
                        MERGE (j)-[:CITES]->(av)
                        """,
                        ruling_id=judgment_data["ruling_id"],
                        av_amended=av_amended,
                        av_2015=av_2015,
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
                    nodes.append({
                        "data": {
                            "id": iid,
                            "label": f"بند {props.get('number', '')}",
                            "type": "Item",
                            "hasChildren": False,
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

                # Children: Judgments citing this paragraph
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

        return {"nodes": nodes, "edges": edges}

    # ──────────────────────────────────────────────
    # UTILITIES
    # ──────────────────────────────────────────────

    def clear_db(self):
        """Wipes the database for clean ingestion."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

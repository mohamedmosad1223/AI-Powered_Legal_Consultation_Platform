from src.models.neo4j_model import Neo4jModel


class GraphViewerController:
    def __init__(self):
        self.neo4j = Neo4jModel()

    def get_laws(self):
        """Returns Law nodes only — the tree root."""
        try:
            return self.neo4j.get_law_nodes()
        finally:
            self.neo4j.close()

    def get_children(self, node_id: str, node_type: str):
        """Returns direct children of a node for expand-on-click."""
        try:
            return self.neo4j.get_children(node_id, node_type)
        finally:
            self.neo4j.close()

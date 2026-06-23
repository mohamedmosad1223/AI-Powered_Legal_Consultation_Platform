import os
import glob
import sys
from src.models.docx_parser import DocxParser
from src.models.neo4j_model import Neo4jModel

# Reconfigure stdout for Arabic characters on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

class IngestionController:
    def __init__(self, data_dir=r"d:\Work\AI-Powered_Legal_Consultation_Platform\data"):
        self.data_dir = data_dir
        self.neo4j = Neo4jModel()

    def run_ingestion(self):
        """
        Clears DB, scans data dir, parses and ingests files.
        """
        print("Initializing database connection...")
        self.neo4j.init_db()
        
        print("Clearing existing database contents...")
        self.neo4j.clear_db()

        # 1. Locate law files
        law_2015_path = None
        law_amended_path = None
        judgments_paths = []

        files = glob.glob(os.path.join(self.data_dir, "*.docx"))
        for f in files:
            name = os.path.basename(f)
            if "قانون رقم 34" in name:
                if "كما في 01-01-2015" in name:
                    law_2015_path = f
                else:
                    law_amended_path = f
            elif "الحكم" in name:
                judgments_paths.append(f)

        # 2. Ingest 2015 Law
        if law_2015_path:
            print(f"Parsing 2015 Law version: {os.path.basename(law_2015_path)}")
            law_data_2015 = DocxParser.parse_law(law_2015_path)
            self.neo4j.insert_law(law_data_2015, version_name="2015")
            print("Successfully ingested 2015 Law.")

        # 3. Ingest Amended Law (which replaces or updates the 2015 version where changed)
        if law_amended_path:
            print(f"Parsing Amended Law version: {os.path.basename(law_amended_path)}")
            law_data_amended = DocxParser.parse_law(law_amended_path)
            self.neo4j.insert_law(law_data_amended, version_name="amended")
            print("Successfully ingested Amended Law.")

        # 4. Ingest Judgments
        for j_path in judgments_paths:
            print(f"Parsing Judgment: {os.path.basename(j_path)}")
            judgment_data = DocxParser.parse_judgment(j_path)
            self.neo4j.insert_judgment(judgment_data)
            print(f"Successfully ingested Judgment: {judgment_data['ruling_id']}")

        print("Ingestion completed successfully.")
        self.neo4j.close()

if __name__ == "__main__":
    controller = IngestionController()
    controller.run_ingestion()

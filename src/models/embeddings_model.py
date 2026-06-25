import os
import cohere
from dotenv import load_dotenv

load_dotenv()

class EmbeddingsModel:
    def __init__(self):
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            print("WARNING: COHERE_API_KEY not found in environment variables.")
            self.client = None
        else:
            self.client = cohere.Client(api_key)
            
        # Using the multilingual v3 model as it's the state of the art for Arabic/Multilingual
        self.model_name = "embed-multilingual-v3.0"
        self.vector_size = 1024 # Cohere v3 multilingual produces 1024-d vectors

    def embed_texts(self, texts: list[str], input_type: str = "search_document") -> list[list[float]]:
        """
        Embeds a list of texts.
        input_type can be:
        - "search_document": for documents to store in the DB
        - "search_query": for the user's search query
        """
        if not self.client:
            raise ValueError("Cohere client is not initialized. Please check COHERE_API_KEY.")
            
        if not texts:
            return []
            
        response = self.client.embed(
            texts=texts,
            model=self.model_name,
            input_type=input_type
        )
        return response.embeddings
        
    def embed_query(self, text: str) -> list[float]:
        """Embeds a single query string."""
        return self.embed_texts([text], input_type="search_query")[0]

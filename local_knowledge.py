import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

class LocalKnowledgeBase:
    def __init__(self, model_name='all-MiniLM-L6-v2', dim=384):
        self.model = SentenceTransformer(model_name)
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim)
        self.texts = []
        self.embeddings = []

    def add_entry(self, text):
        # If text is in the format 'P: ...\nN: ...', extract only the narrative for storage
        narrative = text
        if '\nN:' in text:
            parts = text.split('\nN:', 1)
            narrative = parts[1].strip()
        embedding = self.model.encode([text])[0]
        self.index.add(np.array([embedding], dtype='float32'))
        self.texts.append(narrative)
        self.embeddings.append(embedding)

    def search(self, query, top_k=1):
        if not self.texts:
            return []
        embedding = self.model.encode([query])[0]
        D, I = self.index.search(np.array([embedding], dtype='float32'), top_k)
        # Proteger si FAISS devuelve listas vacías o de forma inesperada
        if not isinstance(D, np.ndarray) or not isinstance(I, np.ndarray):
            return []
        if D.shape[0] == 0 or I.shape[0] == 0:
            return []
        if D.shape[1] == 0 or I.shape[1] == 0:
            return []
        results = []
        for idx, dist in zip(I[0], D[0]):
            if 0 <= idx < len(self.texts):
                results.append({'text': self.texts[idx], 'score': 1.0 - dist / 2})
        return results

    def most_similar(self, query, threshold=0.80):
        results = self.search(query, top_k=1)
        if results and results[0]['score'] >= threshold:
            # Return only the narrative (already stored as such)
            return results[0]['text'], results[0]['score']
        return None, 0.0

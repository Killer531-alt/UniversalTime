
class LocalKnowledgeBase:
    def __init__(self):
        self.texts = []

    def add_entry(self, text):
        # Solo almacena el texto relevante (narrativa)
        narrative = text
        if '\nN:' in text:
            parts = text.split('\nN:', 1)
            narrative = parts[1].strip()
        self.texts.append(narrative)

    def search(self, query, top_k=1):
        # Búsqueda muy ligera: coincidencia de palabras clave (puedes mejorar con TF-IDF si quieres)
        if not self.texts:
            return []
        scored = []
        qwords = set(query.lower().split())
        for t in self.texts:
            tw = set(t.lower().split())
            score = len(qwords & tw) / (len(qwords | tw) + 1e-6)
            scored.append((score, t))
        scored.sort(reverse=True)
        return [{'text': t, 'score': s} for s, t in scored[:top_k]]

    def most_similar(self, query, threshold=0.20):
        results = self.search(query, top_k=1)
        if results and results[0]['score'] >= threshold:
            return results[0]['text'], results[0]['score']
        return None, 0.0

# Instrucciones de ejecución para el backend Flask optimizado con Groq y embeddings locales

## 1. Requisitos
- Python 3.11+
- Variables de entorno:
  - `GROQ_API_KEY` (tu API key de Groq)
  - `GROQ_MODEL` (opcional, por defecto: meta-llama/llama-4-scout-17b-16e-instruct)

## 2. Instalación de dependencias

```bash
pip install flask faiss-cpu sentence-transformers httpx tiktoken
```

## 3. Ejecución

```bash
python app.py
```

## 4. Uso del endpoint optimizado

POST `/ai/message`

Body JSON:
```
{
  "playerId": "string",
  "message": "string"
}
```

Respuesta JSON:
```
{
  "reply": "string",
  "source": "local" | "llm",
  "tokensUsed": number
}
```

## 5. Notas
- El sistema responde desde la base local si la similitud es alta (>0.80), usando el LLM solo como último recurso.
- El control de rate limit y tokens está integrado.
- Para escalar concurrencia, migrar la cola de rate limit y el contexto de jugadores a Redis.
- Para persistir FAISS, usar `faiss.write_index` y `faiss.read_index`.
- Si pasas a plan pago de Groq, solo ajusta los límites en `ai_api.py`.

## 6. Seguridad
- Nunca expongas tu API key en el código ni en logs.
- Manejo de errores robusto y sin detalles internos en respuestas.

---

Para dudas o mejoras, revisa los archivos `ai_api.py` y `local_knowledge.py`.

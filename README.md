# Juego Narrativo Multiverse (MVP)


Proyecto mínimo en Flask que usa JSON para persistencia y modelos locales gratuitos para embeddings y generación de texto.

Requisitos:

- Python 3.10+

Instalación:

```bash
python -m venv .venv
.venv\Scripts\activate   # PowerShell: . .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nota: los paquetes `transformers`, `torch`, `sentence-transformers` y `diffusers` pueden descargar pesos de modelos la primera vez que se usan. No se necesita clave de API.

Usar:

```bash
python app.py
```

API endpoints:

- `GET /api/multiverse` — devuelve el multiverso (archivo JSON)
- `POST /api/action` — enviar una acción de estudiante (JSON):

```json
{
  "student": "Juan Pérez",
  "universe_id": "u1",
  "character_id": "ironman_juan",
  "prompt": "Quiero construir un reactor más potente",
  "class_number": 3
}
```

Archivos de datos: `data/` contiene `multiverse.json`, `events.json`, `universes.json`, `characters.json`.

Notas:

- No usa servicios de pago ni claves externas.
- Embeddings: `sentence-transformers` (local).
- Generación de texto: `transformers` (local, modelo pequeño por defecto).
- Generación de imágenes: opcional. Si tienes pesos de Stable Diffusion locales, define `SD_MODEL_PATH` con la ruta al modelo para que el sistema genere imágenes; si no, las imágenes se omiten.
- La búsqueda semántica es local y usa similitud coseno.
- El LLM local intenta devolver un JSON con `effects` y `narrative`. Si no es JSON, el texto se guarda como narración.

Ollama (opcional)

- Para usar Ollama como backend LLM local y dejar que tu Flask app lo consuma, instala Ollama y un modelo (por ejemplo `gemma3:1b`).
- Activa la integración poniendo la variable de entorno `OLLAMA_ENABLED=1` y opcionalmente `OLLAMA_MODEL=gemma3:1b` y `OLLAMA_URL=http://127.0.0.1:11434`.
- Cuando `OLLAMA_ENABLED=1` la aplicación usará la API REST de Ollama para generación de texto. Si Ollama no responde, la app volverá al generador local.

Ejemplo (PowerShell):

```powershell
setx OLLAMA_ENABLED 1
setx OLLAMA_MODEL "gemma3:1b"
setx OLLAMA_URL "http://127.0.0.1:11434"
```

Probar la integración:

```powershell
# arrancar ollama serve en otra terminal
ollama serve
# arrancar la app Flask
python app.py
# en otra terminal probar endpoint
curl -X POST http://127.0.0.1:5000/api/action -H "Content-Type: application/json" -d '{"student":"Juan","universe_id":"u1","character_id":"ironman_juan","prompt":"Ataco al villano","class_number":1}'
```

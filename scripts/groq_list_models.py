import requests
import os

api_key = os.environ.get("GROQ_API_KEY", "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")
url = "https://api.groq.com/openai/v1/models"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

response = requests.get(url, headers=headers)

models = response.json().get('data', [])

# Tabla de consumo aproximado (TPM: tokens per minute, menor es mejor para menos consumo)
# Si hay varios con el mismo consumo bajo, elige el de menor tamaño (menos parámetros)
# Modelos y su consumo (TPM extraído de tu tabla, menor es mejor)
model_consumption = {
    "canopylabs/orpheus-arabic-saudi": 1200,
    "canopylabs/orpheus-v1-english": 1200,
    "groq/compound": 70000,
    "groq/compound-mini": 70000,
    "llama-3.1-8b-instant": 6000,
    "llama-3.3-70b-versatile": 12000,
    "meta-llama/llama-4-maverick-17b-128e-instruct": 6000,
    "meta-llama/llama-4-scout-17b-16e-instruct": 30000,
    "meta-llama/llama-guard-4-12b": 15000,
    "meta-llama/llama-prompt-guard-2-22m": 15000,
    "meta-llama/llama-prompt-guard-2-86m": 15000,
    "moonshotai/kimi-k2-instruct": 10000,
    "moonshotai/kimi-k2-instruct-0905": 10000,
    "openai/gpt-oss-120b": 8000,
    "openai/gpt-oss-20b": 8000,
    "openai/gpt-oss-safeguard-20b": 8000,
    "qwen/qwen3-32b": 6000,
    "whisper-large-v3": float('inf'),
    "whisper-large-v3-turbo": float('inf'),
}

# Filtrar solo los modelos disponibles y con consumo conocido
available = [m['id'] for m in models if m['id'] in model_consumption]
if not available:
    print("No hay modelos disponibles con consumo conocido.")
else:
    # Elegir el de menor consumo
    best = min(available, key=lambda m: model_consumption[m])
    print(f"Modelo con menor consumo: {best} (TPM: {model_consumption[best]})")
    print("Todos los modelos disponibles:", available)

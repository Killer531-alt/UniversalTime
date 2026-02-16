import os
import time
import asyncio
from flask import Blueprint, request, jsonify
from local_knowledge import LocalKnowledgeBase
import numpy as np
import requests
import tiktoken

# Configuración

DEFAULT_OLLAMA_MODEL = "gpt-oss:120b"
MAX_INPUT_TOKENS = 150
MAX_OUTPUT_TOKENS = 350
SIMILARITY_THRESHOLD = 0.80
RATE_LIMIT_RPM = 80
TOKEN_LIMIT_TPM = 30000

# Inicialización
kb = LocalKnowledgeBase()
rate_limit_queue = []  # timestamps de requests
player_context = {}  # playerId: [mensajes]

bp = Blueprint('ai', __name__)

# Utilidad para estimar tokens
try:
    enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
except Exception:
    enc = tiktoken.get_encoding("cl100k_base")

def estimate_tokens(text):
    return len(enc.encode(text))

def cleanup_rate_limit():
    now = time.time()
    while rate_limit_queue and now - rate_limit_queue[0] > 60:
        rate_limit_queue.pop(0)

def can_make_request():
    cleanup_rate_limit()
    return len(rate_limit_queue) < RATE_LIMIT_RPM

def register_request():
    rate_limit_queue.append(time.time())


# --- SIEMPRE usar OllamaFreeAPI con modelo forzado ---
def get_available_ollama_model(preferred=DEFAULT_OLLAMA_MODEL):
    # Solo retorna el modelo preferido, ya que la API oficial requiere nombre exacto
    return preferred

def call_ollama_llm(message, context=None, model_name=None):
    prompt = build_game_prompt(context, message)
    model = get_available_ollama_model(model_name or DEFAULT_OLLAMA_MODEL)
    print(f"[AI_API] Usando modelo oficial Ollama: {model}")
    api_key = os.environ.get("OLLAMA_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    # Construir historial de mensajes para el endpoint /api/chat
    messages = []
    # Mensaje de sistema (instrucción)
    messages.append({"role": "system", "content": prompt})
    # Mensaje del usuario
    messages.append({"role": "user", "content": message})
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": MAX_OUTPUT_TOKENS
        }
        # No se incluye 'format' para máxima compatibilidad
    }
    try:
        r = requests.post("https://ollama.com/api/chat", json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        print(f"[AI_API] Respuesta cruda Ollama: {data}")
        msg = data.get("message", {})
        reply = msg.get("content", "")
        if not reply:
            # Si no hay respuesta, usar thinking como fallback
            reply = msg.get("thinking", "[Sin respuesta de Ollama]")
        tokens_used = data.get("eval_count", len(reply.split()))
        return reply, tokens_used
    except Exception as e:
        print(f"[AI_API] Error Ollama API (modelo {model}): {e}")
        return f"[El sistema está saturado o el modelo '{model}' no está disponible. Intenta más tarde o cambia de modelo.]", 0

def build_game_prompt(context, user_message):
    base_instruction = (
        "Eres un Game Master de un juego de rol multijugador. Responde SOLO con JSON válido, sin texto extra, sin explicaciones, sin markdown.\n\n"
        "Formato ESTRICTO: {\"effects\": {NUMEROS}, \"narrative\": \"TEXTO\", \"choices\": [opciones]}\n\n"
        "effects: SOLO estas claves (todas opcionales): 'points', 'money', 'lifePercent'.\n"
        "narrative: 1-2 frases breves en español, usando el contexto y la historia del jugador si está disponible.\n"
        "choices: 2-3 opciones de acción, cada una string o {\"description\": string, \"effects\": {...}}.\n\n"
        "Ejemplo de respuesta:\n"
        '{"effects": {"points": 100, "money": 200, "lifePercent": -2}, "narrative": "Encuentras un cofre y obtienes 100 monedas, pero pierdes 2% de vida por una trampa.", "choices": ["Seguir explorando", "Volver al campamento"]}'
        "\nNO agregues texto antes ni después del JSON. Si no sabes qué responder, usa: {\"effects\": {}, \"narrative\": \"No puedo responder a eso.\"}"
    )
    
    prompt = base_instruction
    if context:
        prompt += f"\n\n{context}"
    prompt += f"\n\nStudent action: {user_message}"
    return prompt

@bp.route('/ai/message', methods=['POST'])
def ai_message():
    data = request.json or {}
    player_id = data.get('playerId')
    message = data.get('message', '')
    if not player_id or not message:
        return jsonify({'error': 'playerId and message required'}), 400
    # Limitar tokens de entrada
    if estimate_tokens(message) > MAX_INPUT_TOKENS:
        return jsonify({'error': 'Mensaje demasiado largo'}), 400
    # Buscar en base local
    local_reply, score = kb.most_similar(message, threshold=SIMILARITY_THRESHOLD)
    if local_reply:
        print(f"[AI_API] Respuesta local encontrada (score={score:.2f}) para playerId={player_id}")
        return jsonify({'reply': local_reply, 'source': 'local', 'tokensUsed': 0})
    # Rate limit
    if not can_make_request():
        print(f"[AI_API] Rate limit alcanzado para playerId={player_id}")
        return jsonify({'reply': '[Límite de uso alcanzado, intenta en unos segundos]', 'source': 'llm', 'tokensUsed': 0}), 429
    register_request()
    # Contexto resumido
    context = None
    if player_id in player_context:
        ctx = player_context[player_id]
        ctx_text = ' '.join(ctx)
        if estimate_tokens(ctx_text) > 1000:
            ctx_text = ctx_text[-1000:]
        context = ctx_text
    # Llamada a Groq con la librería oficial
    print(f"[AI_API] Enviando petición a OllamaFreeAPI para playerId={player_id}")
    reply, tokens_used = call_ollama_llm(message, context)
    print(f"[AI_API] Respuesta OllamaFreeAPI recibida para playerId={player_id}, tokens usados: {tokens_used}")
    # Procesar JSON si es posible
    narrative = reply
    effects = {}
    choices = []
    imageNote = None
    event_id = None
    import json as _json
    import uuid
    def try_repair_json(s):
        s = s.strip()
        if not s.endswith('}'):  # Si falta cerrar
            s += '"}' if s.count('"') % 2 == 1 else '}'
        if 'choices' in s and s.count('[') > s.count(']'):
            s += ']'
        return s
    json_found = False
    try:
        start = reply.find('{')
        end = reply.rfind('}')
        json_text = None
        if start != -1 and end != -1 and end > start:
            json_text = reply[start:end+1]
        elif start != -1:
            json_text = try_repair_json(reply[start:])
        if json_text:
            try:
                data = _json.loads(json_text)
                narrative = data.get('narrative', narrative)
                effects = data.get('effects', {})
                choices = data.get('choices', [])
                imageNote = data.get('image_note', None)
                json_found = True
            except Exception as e2:
                print(f"[AI_API] Reparación de JSON fallida: {e2}")
    except Exception as e:
        print(f"[AI_API] No se pudo extraer JSON de la respuesta Ollama: {e}")
    import re
    if not json_found:
        # Fallback: intentar extraer efectos y opciones con regex si no hay JSON
        effects = {}
        m_points = re.search(r'(\+|\-)?\d+\s*(puntos|points)', reply, re.IGNORECASE)
        m_money = re.search(r'(\+|\-)?\d+\s*(monedas|dinero|money)', reply, re.IGNORECASE)
        m_life = re.search(r'(\+|\-)?\d+\s*%?\s*(vida|life)', reply, re.IGNORECASE)
        if m_points:
            effects['points'] = int(re.search(r'(\+|\-)?\d+', m_points.group()).group())
        if m_money:
            effects['money'] = int(re.search(r'(\+|\-)?\d+', m_money.group()).group())
        if m_life:
            effects['lifePercent'] = int(re.search(r'(\+|\-)?\d+', m_life.group()).group())
        # Opciones: buscar líneas que empiecen con "Opciones:" o "Options:"
        choices = []
        m_choices = re.search(r'(Opciones|Options)\s*[:：]\s*(.+)', reply, re.IGNORECASE)
        if m_choices:
            # Separar por , o ;
            raw = m_choices.group(2)
            for opt in re.split(r'[;,]', raw):
                opt = opt.strip()
                if opt:
                    choices.append(opt)
    # Generar y guardar un evento real si hay choices
    event_id = None
    if choices:
        # Obtener info de universo y personaje si es posible
        universe_id = None
        character_id = None
        student = None
        class_number = 1
        # Buscar en el mensaje o contexto si hay info
        # Si el player_id es igual al character_id, usarlo
        character_id = player_id
        # Buscar nombre de estudiante si viene en el mensaje
        if 'student' in data:
            student = data['student']
        # Buscar universo si viene en el mensaje
        if 'universe_id' in data:
            universe_id = data['universe_id']
        # Buscar class_number si viene en el mensaje
        if 'class_number' in data:
            class_number = data['class_number']
        # Si no, intentar deducir de storage
        try:
            from storage import Storage
            import os as _os
            storage = Storage(_os.path.join(_os.path.dirname(__file__), 'data'))
            chars = storage.load_characters()
            char = next((c for c in chars if c.get('id') == character_id), None)
            if char:
                student = student or char.get('student') or char.get('name')
                universe_id = universe_id or char.get('currentUniverse')
        except Exception as e:
            print(f"[AI_API] No se pudo deducir info de personaje/universo: {e}")
        import datetime
        event_id = str(uuid.uuid4())
        event = {
            'id': event_id,
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'universe_id': universe_id,
            'character_id': character_id,
            'student': student,
            'prompt': message,
            'class_number': class_number,
            'choices': choices,
            'result': None,
            'embedding': None
        }
        try:
            storage.append_event(event)
        except Exception as e:
            print(f"[AI_API] No se pudo guardar el evento con opciones: {e}")
    # Guardar contexto
    player_context.setdefault(player_id, []).append(message)
    player_context[player_id] = player_context[player_id][-20:]
    # Aprendizaje: guardar solo la narrativa en embeddings locales
    if narrative and narrative != '[El sistema está saturado. Intenta más tarde]':
        kb.add_entry(narrative)
    # Si la narrativa es vacía, mostrar mensaje claro
    if not narrative or narrative.strip() == "Sin respuesta":
        narrative = "[El modelo no devolvió una respuesta. Intenta de nuevo o cambia el prompt.]"
    return jsonify({'reply': narrative, 'effects': effects, 'choices': choices, 'imageNote': imageNote, 'source': 'llm', 'tokensUsed': tokens_used, 'eventId': event_id})

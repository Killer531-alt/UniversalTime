# IMPORTS
import os
from evaluation import calculate_final_grade
import uuid
import json
# Configurar la API key de Ollama.com para todo el backend
os.environ["OLLAMA_API_KEY"] = "4d8096350fbd448cb71ce635a6092075.zYanmZA03H90lj1wM7q8U8Qw"
from flask import Flask, request, jsonify, send_file, render_template_string
from ai_api import bp
from storage import Storage
from ai import AI

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.register_blueprint(bp)
data_dir = os.path.join(os.path.dirname(__file__), 'data')
storage = Storage(data_dir)
ai = AI()


@app.route('/')
def index():
    """Serve the main chat interface."""
    return send_file('static/index.html')


@app.route('/api/multiverse', methods=['GET'])
def get_multiverse():
    mv = storage.load_multiverse()
    return jsonify(mv)


@app.route('/api/characters', methods=['GET'])
def get_characters():
    """Return list of all characters."""
    chars = storage.load_characters()
    return jsonify({'characters': chars if isinstance(chars, list) else []})


@app.route('/api/universes', methods=['GET'])
def get_universes():
    """Return list of all universes."""
    univs = storage.load_universes()
    return jsonify({'universes': univs if isinstance(univs, list) else []})


@app.route('/api/character/<character_id>', methods=['GET'])
def get_character(character_id):
    """Return a specific character."""
    chars = storage.load_characters()
    if isinstance(chars, list):
        for c in chars:
            if c.get('id') == character_id:
                return jsonify(c)
    return jsonify({'error': 'not found'}), 404


@app.route('/api/universe/<universe_id>', methods=['GET'])
def get_universe(universe_id):
    """Return a specific universe."""
    univ = storage.load_universe(universe_id)
    if univ:
        return jsonify(univ)
    return jsonify({'error': 'not found'}), 404


@app.route('/api/action', methods=['POST'])
def handle_action():
    payload = request.json or {}
    required = ['student', 'universe_id', 'character_id', 'prompt', 'class_number']
    for r in required:
        if r not in payload:
            return jsonify({'error': f'missing {r}'}), 400

    # Validate action against rules
    valid = storage.validate_action(payload)
    if not valid.get('valid', False):
        return jsonify({'error': 'action invalid', 'detail': valid}), 400

    # Create event
    event = storage.create_event(payload)

    # If validation suggests pre-effects (e.g., change_universe costs), attach them
    if valid.get('change_universe'):
        event.setdefault('pre_effects', valid.get('effects'))

    # Create embedding for the prompt + minimal context
    embedding = ai.get_embedding(payload['prompt'])
    event['embedding'] = embedding.tolist()
    storage.append_event(event)

    # Search similar events for context and also include recent universe events
    events = storage.load_events()
    top = ai.search_similar(embedding, events, top_k=5)
    # include last N events from the same universe to ensure full context
    try:
        recent_events = [e for e in events if e.get('universe_id') == payload.get('universe_id')]
        recent_events = recent_events[-30:]
    except Exception:
        recent_events = []
    # combine similar events and recent timeline (deduplicate by id preserving order)
    combined = []
    ids = set()
    for e in (list(top) + list(recent_events)):
        if not e or not isinstance(e, dict):
            continue
        eid = e.get('id')
        if eid in ids:
            continue
        ids.add(eid)
        combined.append(e)

    # Load character for context
    characters = storage.load_characters()
    current_char = None
    for c in characters:
        if c.get('id') == payload['character_id']:
            current_char = c
            break

    # Build prompt for LLM: rules + character context + recent events
    universe = storage.load_universe(payload['universe_id'])
    system_prompt = ai.build_system_prompt(universe, current_char, combined)

    # Ask LLM to interpret and propose changes (expects JSON in reply)
    response_text = ai.generate_narrative(system_prompt, payload['prompt'])

    # Apply effects suggested by the LLM (assumed JSON)
    try:
        result = storage.apply_event_result(event, response_text)
    except Exception as e:
        return jsonify({'error': 'failed to apply result', 'detail': str(e)}), 500

    # Load updated character (if available from result) so UI can refresh stats
    updated_character = None
    if isinstance(result, dict) and 'character' in result and result['character']:
        updated_character = result['character']
    else:
        # fallback: reload from storage
        chars = storage.load_characters()
        for c in chars:
            if c.get('id') == event['character_id']:
                updated_character = c
                break

    # Optionally generate image for the class
    if universe.get('enable_images'):
        img_path = ai.generate_image_for_event(universe, event, payload['class_number'])
        if img_path:
            event['image'] = img_path
        else:
            event['image'] = None
            event['image_note'] = 'image_not_generated: configure SD_MODEL_PATH with a local Stable Diffusion model'
        storage.update_event(event['id'], event)

    # If the LLM returned choices, include them in response and optionally generate images for choices
    event_choices = event.get('choices') or []
    for choice in event_choices:
        # if choice has an image_prompt, try to generate a thumbnail
        if isinstance(choice, dict) and choice.get('image_prompt'):
            img = ai.generate_image_for_event(universe, {'universe_id': universe.get('id'), 'prompt': choice.get('image_prompt'), 'id': event['id'] + '_' + str(event_choices.index(choice)) , 'result': {'narrative': choice.get('description', '')}}, payload['class_number'])
            if img:
                choice['image'] = img
    if event_choices:
        event['choices'] = event_choices
        storage.update_event(event['id'], event)

    # Remove embedding from response (keep internally, but not in API response)
    event_response = {k: v for k, v in event.items() if k != 'embedding'}

    # Add image note if generation was attempted but failed
    if universe.get('enable_images') and not event_response.get('image'):
        event_response['image_note'] = 'Configure SD_MODEL_PATH to generate images'

    return jsonify({'event': event_response, 'narrative': response_text, 'applied': result, 'character': updated_character})


@app.route('/api/choice', methods=['POST'])
def apply_choice():
    """Apply a previously offered choice from an event. Body: { event_id, choice_index, student, class_number }
    """
    payload = request.json or {}
    idx = int(payload.get('choice_index', 0))
    student = payload.get('student')
    class_number = payload.get('class_number', 1)
    # Recibir la descripción de la opción seleccionada
    # El frontend debe enviar el texto de la opción seleccionada (description)
    choice_text = payload.get('choice_text')
    character_id = payload.get('character_id') or payload.get('student') or ''
    universe_id = payload.get('universe_id')
    # Si no se recibe, error
    if not choice_text or not character_id:
        return jsonify({'error': 'missing choice_text or character_id'}), 400
    # Llamar al LLM como si fuera un nuevo mensaje
    from ai_api import call_ollama_llm
    # Opcional: contexto del personaje
    context = None
    try:
        chars = storage.load_characters()
        char = next((c for c in chars if c.get('id') == character_id), None)
        if char:
            context = f"Historial: {char.get('history', [])}"
    except Exception:
        pass
    reply, tokens_used = call_ollama_llm(choice_text, context)
    # Procesar respuesta del LLM (igual que en /ai/message)
    import json as _json
    import re
    narrative = reply
    effects = {}
    choices = []
    imageNote = None
    json_found = False
    try:
        start = reply.find('{')
        end = reply.rfind('}')
        json_text = None
        if start != -1 and end != -1 and end > start:
            json_text = reply[start:end+1]
        elif start != -1:
            json_text = reply[start:]
        if json_text:
            try:
                data = _json.loads(json_text)
                narrative = data.get('narrative', narrative)
                effects = data.get('effects', {})
                choices = data.get('choices', [])
                imageNote = data.get('image_note', None)
                json_found = True
            except Exception:
                pass
    except Exception:
        pass
    if not json_found:
        m_points = re.search(r'(\+|\-)?\d+\s*(puntos|points)', reply, re.IGNORECASE)
        m_money = re.search(r'(\+|\-)?\d+\s*(monedas|dinero|money)', reply, re.IGNORECASE)
        m_life = re.search(r'(\+|\-)?\d+\s*%?\s*(vida|life)', reply, re.IGNORECASE)
        if m_points:
            effects['points'] = int(re.search(r'(\+|\-)?\d+', m_points.group()).group())
        if m_money:
            effects['money'] = int(re.search(r'(\+|\-)?\d+', m_money.group()).group())
        if m_life:
            effects['lifePercent'] = int(re.search(r'(\+|\-)?\d+', m_life.group()).group())
    # Aplicar efectos al personaje
    # Crear y guardar evento
    import datetime
    event_id = None
    try:
        from storage import Storage
        import os as _os
        storage2 = Storage(_os.path.join(_os.path.dirname(__file__), 'data'))
        event_id = str(uuid.uuid4())
        event = {
            'id': event_id,
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'universe_id': universe_id,
            'character_id': character_id,
            'student': student,
            'prompt': f"CHOICE: {choice_text}",
            'class_number': class_number,
            'choices': [],
            'result': None,
            'embedding': None
        }
        storage2.append_event(event)
        res = storage2.apply_event_result(event, _json.dumps({'effects': effects, 'narrative': narrative}))
        # Obtener el personaje actualizado
        updated_char = None
        try:
            chars = storage2.load_characters()
            updated_char = next((c for c in chars if c.get('id') == character_id), None)
        except Exception:
            pass
    except Exception as e:
        return jsonify({'error': f'failed to apply result: {e}'}), 500
    return jsonify({'event': event, 'applied': res, 'narrative': narrative, 'effects': effects, 'choices': choices, 'imageNote': imageNote, 'character': updated_char})


@app.route('/api/evaluate/<character_id>', methods=['GET'])
def evaluate_character(character_id):
    """Calculate final grade for a character."""
    try:
        events = storage.load_events()
        characters = storage.load_characters()
        universes = storage.load_universes()
        
        # Find the character
        char = None
        chars_list = characters if isinstance(characters, list) else []
        for c in chars_list:
            if c.get('id') == character_id:
                char = c
                break
        
        if not char:
            return jsonify({'error': f'character {character_id} not found'}), 404
        
        # Build normalized metrics for evaluation (0..1)
        life = char.get('lifePercent', 1.0)
        try:
            life = float(life)
            if life > 1:
                life = life / 100.0
        except Exception:
            life = 1.0

        points = float(char.get('points', 0))
        money = float(char.get('money', 0))
        history_len = len(char.get('history', []) if isinstance(char.get('history', []), list) else [])

        # Normalize heuristics (tunable)
        metrics = {
            'multiverse': min(storage.load_multiverse().get('totalPoints', 0) / 10000.0, 1.0),
            'universe': 0.0,
            'character': min(points / 5000.0, 1.0),
            'life': max(0.0, min(1.0, life)),
            'points': min(points / 5000.0, 1.0),
            'money': min(money / 5000.0, 1.0),
            'hetero': 0.0,
            'auto': 0.0,
            'professor': 0.0,
        }

        # Universe-specific score (simple): based on universe totals
        try:
            uni = storage.load_universe(char.get('currentUniverse'))
            if uni:
                metrics['universe'] = min(uni.get('totalPoints', 0) / 10000.0, 1.0)
        except Exception:
            pass

        # Turn history length into a participation score
        metrics['character'] = min(1.0, metrics['character'] + min(history_len / 20.0, 0.2))

        # incorporate stored evaluations for this character
        evals = storage.load_evaluations()
        # compute averages for hetero/auto/professor for this character
        hetero_scores = [e.get('score') for e in evals if e.get('character_id') == character_id and e.get('kind') == 'hetero']
        auto_scores = [e.get('score') for e in evals if e.get('character_id') == character_id and e.get('kind') == 'auto']
        prof_scores = [e.get('score') for e in evals if e.get('character_id') == character_id and e.get('kind') == 'professor']
        def avg(lst):
            return sum(lst)/len(lst)/100.0 if lst else 0.0

        metrics['hetero'] = avg(hetero_scores)
        metrics['auto'] = avg(auto_scores)
        metrics['professor'] = avg(prof_scores)

        # Calculate final grade using evaluation helper
        result = calculate_final_grade(metrics)
        normalized = result.get('normalized_score', 0.0)
        grade_value = round(float(normalized * 100.0), 2)

        return jsonify({
            'character_id': character_id,
            'student': char.get('name', 'Unknown'),
            'grade': grade_value,
            'metrics': metrics,
            'evaluation': result,
            'character': char
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/translate', methods=['POST'])
def translate_text():
    """Translate text to Spanish using Ollama."""
    payload = request.json or {}
    text = payload.get('text', '')
    target_lang = payload.get('target_lang', 'Spanish')
    
    if not text:
        return jsonify({'error': 'missing text'}), 400
    
    try:
        import os
        import requests
        api_key = os.environ.get("OLLAMA_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload_ollama = {
            "model": "deepseek-r1:1.5b",
            "messages": [
                {"role": "system", "content": "Eres un traductor experto. Traduce todo al español, sin explicaciones."},
                {"role": "user", "content": text}
            ],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 200}
        }
        r = requests.post("https://ollama.com/api/chat", json=payload_ollama, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        translation = data.get("message", {}).get("content", "")
        return jsonify({'original': text, 'translated': translation, 'language': target_lang})
    except Exception as e:
        return jsonify({'original': text, 'translated': text, 'language': target_lang, 'error': str(e)}), 200


@app.route('/api/evaluation/submit', methods=['POST'])
def submit_evaluation():
    payload = request.json or {}
    required = ['character_id', 'kind', 'score']
    for r in required:
        if r not in payload:
            return jsonify({'error': f'missing {r}'}), 400
    try:
        evs = storage.load_evaluations() or []
        rec = {
            'id': str(len(evs) + 1) + '_' + payload.get('character_id', '') + '_' + payload.get('kind', ''),
            'character_id': payload.get('character_id'),
            'student': payload.get('student'),
            'kind': payload.get('kind'),
            'score': float(payload.get('score')),
            'comments': payload.get('comments', ''),
            'class_number': payload.get('class_number')
        }
        evs.append(rec)
        storage.save_evaluations(evs)
        return jsonify({'saved': True, 'evaluation': rec})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/missions', methods=['GET'])
def get_missions():
    """Return list of available missions."""
    missions = storage.load_missions() or []
    return jsonify({'missions': missions})


@app.route('/api/market', methods=['GET'])
def get_market():
    items = storage.load_market() or []
    return jsonify({'items': items})


@app.route('/api/market/buy', methods=['POST'])
def buy_market_item():
    payload = request.json or {}
    character_id = payload.get('character_id')
    item_id = payload.get('item_id')
    if not character_id or not item_id:
        return jsonify({'error': 'missing character_id or item_id'}), 400
    chars = storage.load_characters()
    char = next((c for c in chars if c.get('id') == character_id), None)
    if not char:
        return jsonify({'error': 'character not found'}), 404

    market = storage.load_market() or []
    item = next((i for i in market if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': 'item not found'}), 404

    price = float(item.get('price', 0))
    if (char.get('money', 0) or 0) < price:
        return jsonify({'error': 'insufficient funds'}), 400

    # deduct money and add item to inventory
    char['money'] = (char.get('money', 0) or 0) - price
    inv = char.get('inventory') or []
    inv.append(item)
    char['inventory'] = inv

    # save characters
    storage.save_json(storage.characters_path, chars)
    return jsonify({'character': char, 'item': item})


@app.route('/api/inventory/use', methods=['POST'])
def use_inventory_item():
    payload = request.json or {}
    character_id = payload.get('character_id')
    item_id = payload.get('item_id')
    student = payload.get('student')
    class_number = payload.get('class_number', 1)
    if not character_id or not item_id:
        return jsonify({'error': 'missing character_id or item_id'}), 400

    chars = storage.load_characters()
    char = next((c for c in chars if c.get('id') == character_id), None)
    if not char:
        return jsonify({'error': 'character not found'}), 404

    inv = char.get('inventory') or []
    item = next((i for i in inv if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': 'item not in inventory'}), 400

    # Create an event to record item use
    new_payload = {
        'student': student or char.get('student') or char.get('name'),
        'universe_id': char.get('currentUniverse'),
        'character_id': character_id,
        'prompt': f"USE_ITEM: {item.get('name', item_id)}",
        'class_number': class_number,
    }
    new_event = storage.create_event(new_payload)
    storage.append_event(new_event)

    # Apply item effects if provided
    effects = item.get('effects') or {}
    narrative = item.get('use_text') or f"Usas {item.get('name')}"
    try:
        res = storage.apply_event_result(new_event, json.dumps({'effects': effects, 'narrative': narrative}))
    except Exception as e:
        return jsonify({'error': 'failed to apply item effects', 'detail': str(e)}), 500

    # Remove item if consumable
    try:
        consumable = item.get('consumable', True)
        if consumable:
            inv = [i for i in inv if i.get('id') != item_id]
            char['inventory'] = inv
            # save characters
            storage.save_json(storage.characters_path, chars)
    except Exception:
        pass

    # Reload character to get updated state from apply_event_result
    try:
        chars_fresh = storage.load_characters()
        for c in chars_fresh:
            if c.get('id') == character_id:
                char = c
                break
    except Exception:
        pass

    return jsonify({'event': new_event, 'applied': res, 'character': char})




if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# Endpoint para iniciar misión y conectar al LLM
@app.route('/api/mission/start', methods=['POST'])
def start_mission():
    payload = request.json or {}
    mission_id = payload.get('mission_id')
    character_id = payload.get('character_id')
    universe_id = payload.get('universe_id')
    student = payload.get('student')
    class_number = payload.get('class_number', 1)
    if not mission_id or not character_id:
        return jsonify({'error': 'missing mission_id or character_id'}), 400
    missions = storage.load_missions()
    mission = next((m for m in missions if m.get('id') == mission_id), None)
    if not mission:
        return jsonify({'error': 'mission not found'}), 404
    chars = storage.load_characters()
    char = next((c for c in chars if c.get('id') == character_id), None)
    if not char:
        return jsonify({'error': 'character not found'}), 404
    # Construir contexto para el LLM
    context = f"Misión: {mission.get('title')}\nDescripción: {mission.get('description')}\nObjetivo: {mission.get('objective')}\nRecompensa: {mission.get('reward_points')} puntos, {mission.get('reward_money')} monedas\nDificultad: {mission.get('difficulty')}\nPersonaje: {char.get('name')}\nUniverso: {universe_id}"
    prompt = f"INICIA_MISION: {mission.get('title')}\n{context}"
    # Llamar al LLM para generar narrativa
    try:
        narrative = ai.generate_mission_narrative(prompt, char, mission)
    except Exception as e:
        return jsonify({'error': 'LLM error', 'detail': str(e)}), 500
    return jsonify({'narrative': narrative, 'mission': mission})

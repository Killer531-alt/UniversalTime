import json
from local_knowledge import LocalKnowledgeBase
import re

# Cargar base de conocimiento local
kb = LocalKnowledgeBase()

def is_jugable_narrative(narrative):
    if not narrative:
        return False
    # Debe tener al menos 12 palabras y no contener instrucciones ni palabras clave de sistema
    if len(narrative.split()) < 12:
        return False
    # Palabras que suelen indicar instrucciones o texto de sistema
    system_keywords = [
        'Return only a JSON', 'Respond with a JSON', 'Provide a single valid JSON',
        'Student action:', 'Player action:', 'Recent relevant events:',
        'Respond with', 'JSON', 'object with keys', 'no extra explanation',
        'description of the effects', 'Universe:', 'keys', 'effects', 'narrative',
        'valid JSON', 'structure', 'object', 'Provide', 'Reply', 'no text', 'no markdown',
        'no code', 'Respond', 'explanation', 'top-level', 'keys', 'effects', 'narrative',
        'Respond only', 'CRITICAL EXAMPLE', 'Example JSON', 'EFFECTS object', 'DELTA', 'Range:'
    ]
    for kw in system_keywords:
        if kw.lower() in narrative.lower():
            return False
    # No debe ser solo una lista de acciones o eventos
    if re.match(r"^[-•\d\s\w:.,]+$", narrative) and len(set(narrative)) < 20:
        return False
    return True

# Leer eventos y poblar la base
with open('data/events.json', 'r', encoding='utf-8') as f:
    events = json.load(f)

count = 0
for event in events:
    result = event.get('result', {})
    narrative = None
    if isinstance(result, dict):
        narrative = result.get('narrative')
    elif isinstance(result, str):
        narrative = result
    # Solo agregar si es narrativa jugable
    if is_jugable_narrative(narrative):
        kb.add_entry(narrative)
        count += 1

print(f"Base de conocimiento poblada SOLO con {count} narrativas jugables de events.json.")

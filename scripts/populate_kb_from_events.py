import json
from local_knowledge import LocalKnowledgeBase

# Cargar base de conocimiento local
kb = LocalKnowledgeBase()

# Leer eventos y poblar la base
with open('data/events.json', 'r', encoding='utf-8') as f:
    events = json.load(f)

count = 0
for event in events:
    prompt = event.get('prompt')
    result = event.get('result', {})
    narrative = None
    if isinstance(result, dict):
        narrative = result.get('narrative')
    elif isinstance(result, str):
        narrative = result
    # Solo agregar si hay narrativa
    if narrative:
        kb.add_entry(narrative)
        count += 1

print(f"Base de conocimiento poblada con {count} ejemplos de events.json.")

import os
import json
from pathlib import Path

import requests

 


class AI:
    def __init__(self):
        self.ollama_api_key = os.environ.get('OLLAMA_API_KEY', None)
        self.ollama_model = os.environ.get('OLLAMA_MODEL', 'gpt-oss:120b')

    def generate_mission_narrative(self, prompt, character, mission):
        """Genera narrativa específica para una misión usando el LLM."""
        # Usar el generador normal, pero sin requerir JSON, solo narrativa
        try:
            text = self.ollama_generate(prompt)
            try:
                data = json.loads(text)
                return data.get('narrative', text)
            except Exception:
                return text
        except Exception:
            return "No se pudo generar narrativa de misión."

    def _load_embed_model(self):
        """Lazy load embedding model."""
        if self.embed_model is None:
            print(f"Loading embedding model: {self.embed_model_name}...")
            pass
        return self.embed_model

                # Métodos de embeddings y modelos locales eliminados para máxima ligereza
        
        # Add character context
        if character:
            lines.append(f"\nCharacter: {character.get('name', 'Unknown')}")
            lines.append(f"  Role: {character.get('role', 'Adventurer')}")
            lines.append(f"  Life: {(character.get('lifePercent', 1.0) * 100):.0f}%")
            lines.append(f"  Points: {character.get('points', 0)}")
            lines.append(f"  Money: {character.get('money', 0)}")
            
            # Show recent actions from history
            if character.get('history'):
                lines.append("\n  Recent Actions:")
                for h in character.get('history', [])[-3:]:  # last 3 actions
                    if h is None:
                        continue
                    effects = h.get('effects', {}) if h else {}
                    lines.append(f"    - Points: {effects.get('points', 0)}, Money: {effects.get('money', 0)}, Life: {effects.get('lifePercent', 0)}")
        
        # Universe rules
        rules = universe.get('rules', {})
        if rules:
            lines.append('\nUniverse Rules:')
            lines.append(json.dumps(rules, ensure_ascii=False, indent=2))
        
        # Recent events for context (include up to last 30 events from the universe)
        lines.append('\nRecent Story Events:')
        if recent_events:
            for e in recent_events[-30:]:
                if not e or not isinstance(e, dict):
                    continue
                # prefer stored narrative, else prompt
                narrative = None
                result = e.get('result')
                if isinstance(result, dict):
                    narrative = result.get('narrative')
                if not narrative:
                    narrative = e.get('prompt') or '<no prompt>'
                # include effects if present
                effects = None
                if isinstance(result, dict):
                    effects = result.get('effects')
                student = e.get('student', 'Player')
                snippet = (str(narrative)[:200]).replace('\n', ' ')
                if effects:
                    lines.append(f"- {student}: {snippet} (effects: {json.dumps(effects, ensure_ascii=False)})")
                else:
                    lines.append(f"- {student}: {snippet}")
        
        return '\n'.join(lines)

    def generate_narrative(self, system_prompt, user_prompt, max_length: int = 512):
        base_instruction = (
            "You are an immersive Game Master. Respond with a rich, engaging narrative that considers the character's history.\n\n"
            "RESPOND ONLY WITH VALID JSON - nothing else.\n\n"
            "JSON structure: {\"effects\": {NUMBERS}, \"narrative\": \"TEXT\"}\n\n"
            "EFFECTS object MUST use ONLY these lowercase keys (all optional):\n"
            "  - 'points': numeric, positive (rewards) or negative (penalties). Range: -500 to +1000\n"
            "  - 'money': numeric, positive (gain) or negative (loss). Range: -1000 to +5000\n"
            "  - 'lifePercent': numeric DELTA (not absolute!). Use SMALL VALUES: -5, -10, +3, +15, -2. This means PERCENTAGE POINTS LOST/GAINED. -5 = lose 5% of life, +10 = gain 10% of life.\n\n"
            "CRITICAL EXAMPLE:\n"
            "- Character has 100% life\n"
            "- You say lifePercent: -20 (not -100!)\n"
            "- Result: 80% life remaining\n"
            "- NEVER return -100 as a delta; only for total life loss scenarios (very rare)\n\n"
            "Example JSON:\n"
            "{\"effects\": {\"points\": 200, \"money\": 500, \"lifePercent\": -5}, \"narrative\": \"You engage in fierce combat but emerge victorious with minor injuries. You gain 200 experience and discover a treasure chest with 500 gold coins.\"}\n\n"
            "Narrative should be 2-3 sentences, immersive, and reference the character's current situation and history.\n\n"
            "OPTIONAL: You may include a 'choices' array to present closed choices to the player.\n"
            "If you include choices, return an array under the top-level key 'choices' with 2-4 options.\n"
            "Each choice should be either a string or an object {\"description\": string, \"effects\": {...}, \"image_prompt\": optional string}.\n\n"
            "NO other fields in effects. NO markdown. NO code blocks. PURE JSON ONLY."
        )

        prompt = base_instruction + "\n\n" + system_prompt + '\n\nStudent action: ' + user_prompt

        # Try up to two attempts: first normal, then extra strict JSON-only and request choices
        attempts = [
            "CRITICAL: Return ONLY JSON. NO text before/after. The JSON must include keys 'effects' and 'narrative'. Additionally include a 'choices' array with 2-4 closed options (each a string or object {\"description\":string, \"effects\":{...}}). {\"effects\": {\"points\": INT (range -500 to 1000), \"money\": INT (range -1000 to 5000), \"lifePercent\": INT (delta, range -20 to 20)}, \"narrative\": \"2-3 sentence immersive story\", \"choices\": [...]}. Remember: lifePercent is DELTA not absolute!\n\n" + prompt,
            prompt
        ]

        for attempt_prompt in attempts:
            try:
                text = self.groq_generate(attempt_prompt)
            except Exception:
                text = None

            if not text:
                continue

            # Try to extract JSON substring
            try:
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1 and end > start:
                    json_text = text[start:end+1]
                    # Validate JSON
                    import json as _json
                    _json.loads(json_text)
                    return json_text
            except Exception:
                # invalid JSON, try next attempt
                continue

        # If all attempts failed, return raw text from last attempt (so storage can store narrative)
        return text or ''


    def groq_generate(self, prompt_text: str):
        """Call Groq API using OpenAI client."""
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=512,
            temperature=0.3,
        )
        # The response format is similar to OpenAI
        return response.choices[0].message.content.strip()

    def generate_image_for_event(self, universe, event, class_number):
        """No genera imágenes en modo ligero."""
        return None

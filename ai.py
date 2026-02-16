import os
import json
import numpy as np
from pathlib import Path

from openai import OpenAI

from sentence_transformers import SentenceTransformer
from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer


class AI:
    def __init__(self, embed_model_name: str = 'all-MiniLM-L6-v2', gen_model_name: str = 'EleutherAI/gpt-neo-125M'):
        # Embedding model (sentence-transformers) - load lazily
        self.embed_model_name = embed_model_name
        self.embed_model = None

        # Text generation model (transformers) - small model by default
        self.gen_model_name = gen_model_name
        self.tokenizer = None
        self.gen_model = None
        self.generator = None

        # Groq integration (replaces Ollama)
        self.groq_api_key = os.environ.get('GROQ_API_KEY', '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')
        self.groq_model = os.environ.get('GROQ_MODEL', 'canopylabs/orpheus-arabic-saudi')
        self.groq_client = OpenAI(
            api_key=self.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    def generate_mission_narrative(self, prompt, character, mission):
        """Genera narrativa específica para una misión usando el LLM."""
        # Usar el generador normal, pero sin requerir JSON, solo narrativa
        try:
            text = self.groq_generate(prompt)
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
            self.embed_model = SentenceTransformer(self.embed_model_name)
        return self.embed_model

    def _load_gen_model(self):
        """Lazy load text generation model."""
        if self.generator is None:
            print(f"Loading text generation model: {self.gen_model_name}...")
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(self.gen_model_name)
                self.gen_model = AutoModelForCausalLM.from_pretrained(self.gen_model_name)
                self.generator = pipeline('text-generation', model=self.gen_model, tokenizer=self.tokenizer)
            except Exception:
                # Fallback: use a simple pipeline with 'gpt2' if specific model download fails
                print("Falling back to gpt2...")
                self.tokenizer = AutoTokenizer.from_pretrained('gpt2')
                self.gen_model = AutoModelForCausalLM.from_pretrained('gpt2')
                self.generator = pipeline('text-generation', model=self.gen_model, tokenizer=self.tokenizer)
        return self.generator

    def get_embedding(self, text: str):
        model = self._load_embed_model()
        vec = model.encode(text, convert_to_numpy=True)
        return np.array(vec, dtype=float)

    def search_similar(self, query_vec, events, top_k=5):
        candidates = []
        qnorm = np.linalg.norm(query_vec) + 1e-12
        q = query_vec / qnorm
        for e in events:
            if e is None:  # Skip None events
                continue
            if not isinstance(e, dict):  # Only process dict events
                continue
            emb = e.get('embedding')
            if not emb:
                continue
            try:
                v = np.array(emb, dtype=float)
                v = v / (np.linalg.norm(v) + 1e-12)
                score = float(np.dot(q, v))
                candidates.append((score, e))
            except Exception:
                # Skip events with invalid embeddings
                continue
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:top_k]]

    def build_system_prompt(self, universe, character, recent_events):
        lines = []
        lines.append(f"Universe: {universe.get('name', universe.get('id'))}")
        lines.append(f"Description: {universe.get('description', 'A mystical world')}")
        
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
        """Generate a simple image for the event based on narrative/action keywords.
        If SD_MODEL_PATH is set, use Stable Diffusion. Otherwise, use a simple PIL-based generator.
        """
        sd_path = os.environ.get('SD_MODEL_PATH')
        
        # Try Stable Diffusion if configured
        if sd_path:
            try:
                from diffusers import StableDiffusionPipeline
                print(f"[DEBUG] Loading SD from {sd_path}...")
                pipe = StableDiffusionPipeline.from_pretrained(sd_path)
                prompt = universe.get('image_prompt_template') or f"Scene: {event.get('prompt')}"
                print(f"[DEBUG] Generating image with prompt: {prompt}")
                image = pipe(prompt).images[0]
                images_dir = Path(universe.get('image_dir', 'static/images'))
                images_dir.mkdir(parents=True, exist_ok=True)
                filename = images_dir / f"{event['universe_id']}_class{class_number}_{event['id']}.png"
                image.save(filename)
                print(f"[DEBUG] Image saved: {filename}")
                return f"/static/images/{filename.name}"
            except Exception as e:
                print(f"[DEBUG] SD generation failed: {e}")
                # Fall through to simple generator
        
        # Simple PIL-based image generator (no AI needed)
        try:
            from PIL import Image, ImageDraw, ImageFont
            import random
            
            # Extract keywords from narrative for color/theme
            narrative = event.get('result', {}).get('narrative', event.get('prompt', ''))
            keywords = narrative.lower().split()
            
            # Color mapping for keywords
            color_map = {
                'battle': (139, 0, 0),  # dark red
                'fight': (200, 0, 0),   # red
                'magic': (75, 0, 130),  # indigo
                'spell': (75, 0, 130),
                'treasure': (255, 215, 0),  # gold
                'gold': (255, 215, 0),
                'heal': (0, 128, 0),    # green
                'win': (34, 139, 34),   # forest green
                'lose': (64, 64, 64),   # gray
                'death': (0, 0, 0),     # black
                'adventure': (100, 149, 237),  # cornflower
                'explore': (100, 149, 237),
            }
            
            # Determine dominant color
            color = (100, 150, 200)  # default blue
            for keyword, col in color_map.items():
                if keyword in keywords:
                    color = col
                    break
            
            # Create image
            img = Image.new('RGB', (400, 300), color)
            draw = ImageDraw.Draw(img)
            
            # Add decorative elements
            effects = event.get('result', {}).get('effects', {})
            
            # Draw circles/effects based on stats
            points = effects.get('points', 0)
            money = effects.get('money', 0)
            life_delta = effects.get('lifePercent', 0)
            
            # Decorative circles
            circle_y = 80
            if points > 0:
                draw.ellipse([50, circle_y, 120, circle_y + 70], fill=(255, 215, 0), outline=(255, 255, 255), width=2)
                draw.text((65, circle_y + 20), f"+{int(points)}", fill=(0, 0, 0))
            
            if money > 0:
                draw.ellipse([150, circle_y, 220, circle_y + 70], fill=(192, 192, 192), outline=(255, 255, 255), width=2)
                draw.text((160, circle_y + 20), f"${int(money)}", fill=(0, 0, 0))
            
            if life_delta != 0:
                # life_delta may be a fractional delta (0.05) or percentage (5 or -5).
                try:
                    l = float(life_delta)
                except Exception:
                    l = 0
                if abs(l) <= 1:
                    display_delta = int(l * 100)
                else:
                    display_delta = int(l)
                color_delta = (0, 200, 0) if display_delta > 0 else (200, 0, 0)
                draw.ellipse([250, circle_y, 320, circle_y + 70], fill=color_delta, outline=(255, 255, 255), width=2)
                draw.text((265, circle_y + 20), f"{display_delta}%", fill=(255, 255, 255))
            
            # Add border
            draw.rectangle([10, 10, 390, 290], outline=(255, 255, 255), width=3)
            
            # Save
            images_dir = Path('static/images')
            images_dir.mkdir(parents=True, exist_ok=True)
            filename = images_dir / f"{event['universe_id']}_class{class_number}_{event['id']}.png"
            img.save(filename)
            print(f"[DEBUG] PIL image saved: {filename}")
            return f"/static/images/{filename.name}"
            
        except Exception as e:
            print(f"[DEBUG] PIL image generation failed: {e}")
            return None

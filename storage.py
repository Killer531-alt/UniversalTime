import os
import json
import uuid
from datetime import datetime
from filelock import FileLock

# Per-event caps and totals (tighter limits to avoid runaway gains)
MAX_POINTS_DELTA = 100
MAX_MONEY_DELTA = 500
MAX_TOTAL_POINTS = 5000
MAX_TOTAL_MONEY = 5000


class Storage:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.multiverse_path = os.path.join(self.data_dir, 'multiverse.json')
        self.events_path = os.path.join(self.data_dir, 'events.json')
        self.universes_path = os.path.join(self.data_dir, 'universes.json')
        self.characters_path = os.path.join(self.data_dir, 'characters.json')
        self._ensure_files()

    def _ensure_files(self):
        for p, default in [
            (self.multiverse_path, {'name': 'Semestre Demo', 'universes': []}),
            (self.events_path, []),
            (self.universes_path, []),
            (self.characters_path, []),
            (os.path.join(self.data_dir, 'evaluations.json'), []),
            (os.path.join(self.data_dir, 'market.json'), []),
            (os.path.join(self.data_dir, 'missions.json'), []),
        ]:
            if not os.path.exists(p):
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(default, f, ensure_ascii=False, indent=2)

    def _lock(self, path):
        return FileLock(path + '.lock')

    def load_json(self, path):
        lock = self._lock(path)
        with lock:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)

    def save_json(self, path, data):
        lock = self._lock(path)
        with lock:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load_multiverse(self):
        return self.load_json(self.multiverse_path)

    def load_events(self):
        return self.load_json(self.events_path)

    def load_evaluations(self):
        return self.load_json(os.path.join(self.data_dir, 'evaluations.json'))

    def save_evaluations(self, data):
        return self.save_json(os.path.join(self.data_dir, 'evaluations.json'), data)

    def load_market(self):
        return self.load_json(os.path.join(self.data_dir, 'market.json'))

    def save_market(self, data):
        return self.save_json(os.path.join(self.data_dir, 'market.json'), data)

    def load_missions(self):
        return self.load_json(os.path.join(self.data_dir, 'missions.json'))

    def load_universes(self):
        return self.load_json(self.universes_path)

    def load_universe(self, uid):
        us = self.load_universes()
        for u in us:
            if u.get('id') == uid:
                return u
        return {}

    def fork_universe(self, universe_id, reason='paradox'):
        """Create a forked copy of a universe (paradox handling).
        Duplicates universe and characters belonging to it with new ids and links.
        """
        universes = self.load_universes()
        target = None
        for u in universes:
            if u.get('id') == universe_id:
                target = u
                break
        if not target:
            return None

        # Create new universe id
        new_id = f"{target.get('id')}_fork_{int(datetime.utcnow().timestamp())}"
        new_univ = dict(target)
        new_univ['id'] = new_id
        new_univ['name'] = target.get('name', '') + ' (Fork)'
        new_univ['previousState'] = target.get('currentState')
        new_univ['timeline'] = []
        new_univ['fork_reason'] = reason

        universes.append(new_univ)
        self.save_json(self.universes_path, universes)

        # Duplicate characters belonging to original universe
        chars = self.load_characters()
        new_chars = []
        for c in chars:
            if c.get('currentUniverse') == universe_id:
                newc = dict(c)
                newc['id'] = f"{c.get('id')}_fork_{int(datetime.utcnow().timestamp())}"
                newc['originCharacter'] = c.get('id')
                newc['currentUniverse'] = new_id
                # keep history but mark fork
                newc.setdefault('history', []).append({'event_id': None, 'effects': {'note': 'forked copy'}})
                new_chars.append(newc)

        if new_chars:
            chars.extend(new_chars)
            self.save_json(self.characters_path, chars)

        return new_univ

    def validate_action(self, payload):
        # Basic validation following rule 9 and universe change costs.
        # If the character belongs to a different universe, require a change_type (A-E) or assume 'C'.
        chars = self.load_characters()
        universes = self.load_universes()
        char = next((c for c in chars if c.get('id') == payload['character_id']), None)
        # load universe rules if present
        universe = None
        for u in universes:
            if u.get('id') == payload.get('universe_id'):
                universe = u
                break
        if not char:
            return {'valid': True}

        current = char.get('currentUniverse')
        target = payload.get('universe_id')
        if current and current != target:
            change_type = payload.get('change_type', 'C')
            # define simple costs
            costs = {
                'A': {'lifePercent': -50, 'points': -50},
                'B': {'lifePercent': -30, 'points': -20},
                'C': {'lifePercent': -5, 'points': 0},
                'D': {'reset_general': True},
                'E': {'reset_individual': True},
            }
            effect = costs.get(change_type, costs['C'])
            # Enforce universe-level rule: if universe.rules.allow_universe_change == False then reject
            rules = universe.get('rules', {}) if universe else {}
            if rules.get('allow_universe_change') is False:
                return {'valid': False, 'reason': 'universe forbids changing universe'}

            return {'valid': True, 'change_universe': True, 'change_type': change_type, 'effects': effect}

        # Additional global checks: ensure universe has at least 2 students (rule 2)
        try:
            # Count characters assigned to this universe
            chars = self.load_characters()
            count = sum(1 for c in chars if c.get('currentUniverse') == payload.get('universe_id'))
            if count < 2:
                return {'valid': False, 'reason': 'universe must have at least 2 students/characters'}
        except Exception:
            pass

        return {'valid': True}

    def load_characters(self):
        chars = self.load_json(self.characters_path)
        # normalize lifePercent to fraction (0-1)
        try:
            for c in chars:
                if 'lifePercent' in c:
                    lp = c.get('lifePercent')
                    if lp is None:
                        continue
                    # If value looks like percent (>1), convert to fraction
                    try:
                        val = float(lp)
                        if val > 1:
                            c['lifePercent'] = max(0.0, min(1.0, val / 100.0))
                        else:
                            c['lifePercent'] = max(0.0, min(1.0, val))
                    except Exception:
                        c['lifePercent'] = 1.0
        except Exception:
            pass
        return chars

    def create_event(self, payload):
        eid = str(uuid.uuid4())
        event = {
            'id': eid,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'universe_id': payload['universe_id'],
            'character_id': payload['character_id'],
            'student': payload['student'],
            'prompt': payload['prompt'],
            'class_number': payload['class_number'],
            'result': None,
            'embedding': None,
        }
        return event

    def append_event(self, event):
        events = self.load_events()
        events.append(event)
        self.save_json(self.events_path, events)

    def update_event(self, eid, new_event):
        events = self.load_events()
        for i, e in enumerate(events):
            if e.get('id') == eid:
                events[i] = new_event
                self.save_json(self.events_path, events)
                return

    def apply_event_result(self, event, response_text):
        # Expecting LLM to return a JSON string with 'effects' and 'narrative'
        try:
            data = json.loads(response_text)
        except Exception:
            # If not JSON, attempt to extract effects heuristically from the narrative
            cleaned = self._clean_narrative_text(response_text)
            effects = self._parse_effects_from_text(cleaned)
            if effects:
                # apply parsed effects
                data = {'effects': effects, 'narrative': cleaned}
            else:
                event['result'] = {'narrative': cleaned}
                self.update_event(event['id'], event)
                return {'updated': False, 'note': 'narrative only'}

        # Ensure we have a narrative; if LLM returned JSON without narrative, synthesize a short one
        def _synthesize_narrative(effects, event_obj):
            parts = []
            # points
            pts = effects.get('points')
            if pts:
                parts.append(f"gana {int(pts)} puntos" if pts > 0 else f"pierde {abs(int(pts))} puntos")
            # money
            m = effects.get('money')
            if m:
                parts.append(f"obtiene {int(m)} monedas" if m > 0 else f"pierde {abs(int(m))} monedas")
            # life delta
            lp = effects.get('lifePercent')
            if lp is not None:
                try:
                    lpf = float(lp)
                    if abs(lpf) <= 1:
                        delta_pct = int(lpf * 100)
                    else:
                        delta_pct = int(lpf)
                    if delta_pct > 0:
                        parts.append(f"recupera {delta_pct}% de vida")
                    elif delta_pct < 0:
                        parts.append(f"pierde {abs(delta_pct)}% de vida")
                except Exception:
                    pass
            if not parts:
                # fallback to event prompt
                return f"{event_obj.get('prompt', '')}"
            return ' y '.join(parts).capitalize() + '.'

        # Merge effects into character and universe
        effects = data.get('effects', {})
        # capture optional choices produced by the LLM
        choices = data.get('choices') if isinstance(data.get('choices'), list) else None
        if choices:
            event['choices'] = choices
        # Normalize effect keys (handle different capitalizations and synonyms)
        effects = self._normalize_effects(effects)
        # Apply universe difficulty modifiers if present
        try:
            uni = self.load_universe(event.get('universe_id'))
            rules = uni.get('rules', {}) if isinstance(uni, dict) else {}
            difficulty = rules.get('difficulty', 'normal')
            if difficulty == 'hard':
                # Make life losses harsher, reduce positive rewards
                if 'lifePercent' in effects:
                    try:
                        v = float(effects.get('lifePercent'))
                        if v < 0:
                            effects['lifePercent'] = v * 1.5
                    except Exception:
                        pass
                if 'points' in effects and effects.get('points', 0) > 0:
                    try:
                        effects['points'] = int(effects.get('points') * 0.7)
                    except Exception:
                        pass
                if 'money' in effects and effects.get('money', 0) > 0:
                    try:
                        effects['money'] = int(effects.get('money') * 0.7)
                    except Exception:
                        pass
        except Exception:
            pass

        # Clamp per-event numeric deltas to prevent runaway gains
        if 'points' in effects:
            try:
                pv = float(effects['points'])
                pv = max(-MAX_POINTS_DELTA, min(MAX_POINTS_DELTA, pv))
                effects['points'] = int(pv) if pv.is_integer() else pv
            except Exception:
                pass
        if 'money' in effects:
            try:
                mv = float(effects['money'])
                mv = max(-MAX_MONEY_DELTA, min(MAX_MONEY_DELTA, mv))
                effects['money'] = int(mv) if mv.is_integer() else mv
            except Exception:
                pass
        # If narrative missing or empty, create a short synthesized narrative
        if not data.get('narrative'):
            data['narrative'] = _synthesize_narrative(effects, event)
        # Log normalized effects for debugging
        print(f"[DEBUG] Normalized effects: {effects}")
        updated_character = None
        # Update character
        chars = self.load_characters()
        for i, c in enumerate(chars):
            if c.get('id') == event['character_id']:
                # apply numeric effects if present
                for key in ('points', 'money'):
                    if key in effects:
                        c[key] = c.get(key, 0) + effects.get(key, 0)
                # special handling for lifePercent: normalize and store as fraction 0..1
                if 'lifePercent' in effects:
                    cur = c.get('lifePercent', 1.0)
                    try:
                        curf = float(cur)
                        if curf > 1:
                            curf = curf / 100.0
                    except Exception:
                        curf = 1.0

                    eff = effects.get('lifePercent')
                    try:
                        efff = float(eff)
                    except Exception:
                        efff = 0.0

                    # Interpret effect as DELTA (percentage points to add/subtract):
                    # Values between -100 and 100 are treated as percentage deltas
                    # -5 = lose 5%, +10 = gain 10%, -100 = lose all, +50 = gain 50%
                    new_frac = curf
                    if -100 <= efff <= 100:
                        # Treat as percentage delta: convert to fraction
                        delta_frac = efff / 100.0
                        new_frac = max(0.0, min(1.0, curf + delta_frac))
                    else:
                        # If value > 100 or < -100, treat as absolute percentage (legacy)
                        new_frac = max(0.0, min(1.0, efff / 100.0))

                    print(f"[DEBUG] Life update: current={curf:.2f}, effect={efff}, new={new_frac:.2f}")
                    c['lifePercent'] = new_frac
                # append history
                c.setdefault('history', []).append({'event_id': event['id'], 'effects': effects})
                # handle universe change
                if effects.get('change_universe_to'):
                    c['currentUniverse'] = effects.get('change_universe_to')
                chars[i] = c
                updated_character = c
                break
        else:
            # character not found: create minimal with required initial conditions
            newc = {
                'id': event['character_id'],
                'name': event.get('character_id'),
                'student': event.get('student'),
                'history': [{'event_id': event['id'], 'effects': effects}],
                'currentUniverse': event.get('universe_id'),
                'lifePercent': 1.0,
                'points': 0,
                'money': 0,
                'status': 'active'
            }
            chars.append(newc)
            updated_character = newc

        self.save_json(self.characters_path, chars)

        # Update universe totals
        universes = self.load_universes()
        for i, u in enumerate(universes):
            if u.get('id') == event['universe_id']:
                # update totals and clamp to configured maximums
                u['totalPoints'] = u.get('totalPoints', 0) + effects.get('points', 0)
                try:
                    if u['totalPoints'] > MAX_TOTAL_POINTS:
                        u['totalPoints'] = MAX_TOTAL_POINTS
                    if u['totalPoints'] < -MAX_TOTAL_POINTS:
                        u['totalPoints'] = -MAX_TOTAL_POINTS
                except Exception:
                    pass
                u['totalMoney'] = u.get('totalMoney', 0) + effects.get('money', 0)
                try:
                    if u['totalMoney'] > MAX_TOTAL_MONEY:
                        u['totalMoney'] = MAX_TOTAL_MONEY
                    if u['totalMoney'] < -MAX_TOTAL_MONEY:
                        u['totalMoney'] = -MAX_TOTAL_MONEY
                except Exception:
                    pass
                u.setdefault('timeline', []).append({'event_id': event['id'], 'effects': effects})
                universes[i] = u
                break

        self.save_json(self.universes_path, universes)

        event['result'] = data
        self.update_event(event['id'], event)
        return {'updated': True, 'character': updated_character}

    def _normalize_effects(self, effects: dict) -> dict:
        """Coalesce synonymous effect keys into canonical keys: points, money, lifePercent, change_universe_to.
        Preserves numeric signs and converts common variants into consistent numeric types.
        """
        if not isinstance(effects, dict):
            return {}

        normalized = {}

        # Helper to pick numeric value from possibly varied key names
        def pick_and_sum(candidates):
            total = 0
            found = False
            for k in list(effects.keys()):
                if k.lower() in candidates:
                    try:
                        total += float(effects.get(k, 0))
                        found = True
                    except Exception:
                        pass
            return (int(total) if total.is_integer() else total) if found else None

        # Points (including Points, points, Points, Score, ExperiencePoints? treat as points)
        p = pick_and_sum({'points', 'point', 'score', 'experiencepoints', 'experience', 'xp'})
        if p is not None:
            normalized['points'] = p

        # Money synonyms
        m = pick_and_sum({'money', 'currency', 'gold', 'coins', 'cash'})
        if m is not None:
            normalized['money'] = m

        # life percent handling: allow negative deltas or absolute percents
        lp = None
        for k, v in effects.items():
            if k.lower() in ('lifepercent', 'life_percent', 'life', 'hp'):
                try:
                    lp = float(v)
                    break
                except Exception:
                    continue
        if lp is not None:
            normalized['lifePercent'] = lp

        # change universe
        for k, v in effects.items():
            if k.lower() in ('change_universe_to', 'changeuniverse', 'move_to_universe', 'mueve_a_universo'):
                normalized['change_universe_to'] = v
                break

        # Keep any other keys untouched (special actions etc.) but do not overwrite numeric canonical keys
        for k, v in effects.items():
            lk = k.lower()
            if lk in ('points', 'point', 'score', 'experiencepoints', 'experience', 'xp',
                      'money', 'currency', 'gold', 'coins', 'cash',
                      'lifepercent', 'life_percent', 'life', 'hp',
                      'change_universe_to', 'changeuniverse', 'move_to_universe', 'mueve_a_universo'):
                continue
            normalized[k] = v

        return normalized

    def _clean_narrative_text(self, text: str) -> str:
        # Remove obvious instruction lines and repeated tokens
        if not text:
            return ''
        # Normalize whitespace
        txt = text.replace('\r', '\n')
        # Remove common instruction fragments
        remove_phrases = [
            'Return only a JSON object',
            'Provide a single valid JSON object',
            'Respond with a JSON describing effects',
            'Student action:',
            'Player action:',
        ]
        for p in remove_phrases:
            txt = txt.replace(p, '')

        # Collapse repeated words like 'Player action' leftovers
        # If a short token repeats many times, truncate sequence
        # Simple heuristic: if a token repeats >5 times consecutively, keep first occurrence
        parts = txt.splitlines()
        cleaned_lines = []
        for line in parts:
            if not line.strip():
                continue
            # truncate lines with repeated short tokens
            tokens = line.split()
            if tokens:
                # detect repetition of same token
                if len(tokens) > 5 and all(t == tokens[0] for t in tokens[:6]):
                    cleaned_lines.append(tokens[0])
                    continue
            cleaned_lines.append(line)

        res = ' '.join(cleaned_lines).strip()
        # Limit length
        if len(res) > 800:
            res = res[:800] + '...'
        return res

    def _parse_effects_from_text(self, text: str) -> dict:
        # Heuristic extraction for numeric effects: points, money, lifePercent
        import re

        if not text:
            return {}

        effects = {}

        # points: 'gana 10 puntos', 'pierde 5 puntos', 'wins 10 points'
        m = re.search(r"gana\s+(\d+)(?:\s+puntos|\s+points)?", text, re.IGNORECASE)
        if m:
            effects['points'] = int(m.group(1))
        m = re.search(r"pierde\s+(\d+)(?:\s+puntos|\s+points)?", text, re.IGNORECASE)
        if m:
            effects['points'] = effects.get('points', 0) - int(m.group(1))
        m = re.search(r"(\d+)\s+(?:puntos|points)", text, re.IGNORECASE)
        if m and 'points' not in effects:
            effects['points'] = int(m.group(1))

        # money: 'gana 20 dinero', 'gana 20 coins', 'receives 50 money'
        m = re.search(r"gana\s+(\d+)\s+(?:dinero|money|coins)", text, re.IGNORECASE)
        if m:
            effects['money'] = int(m.group(1))
        m = re.search(r"pierde\s+(\d+)\s+(?:dinero|money|coins)", text, re.IGNORECASE)
        if m:
            effects['money'] = effects.get('money', 0) - int(m.group(1))
        m = re.search(r"(\d+)\s+(?:dinero|money|coins)", text, re.IGNORECASE)
        if m and 'money' not in effects:
            effects['money'] = int(m.group(1))

        # life percent: 'pierde 10% de vida', 'life -10%', 'life: 90%'
        m = re.search(r"pierde\s+(\d+)%?\s+de\s+vida", text, re.IGNORECASE)
        if m:
            effects['lifePercent'] = -int(m.group(1))
        m = re.search(r"life[:\s-]+(\d+)%", text, re.IGNORECASE)
        if m:
            # absolute life value
            effects['lifePercent'] = int(m.group(1))
        m = re.search(r"(\d+)%\s+vida", text, re.IGNORECASE)
        if m and 'lifePercent' not in effects:
            effects['lifePercent'] = int(m.group(1))

        # change universe mention: 'moves to universe X', 'change_universe_to: X'
        m = re.search(r"change_universe_to[:\s]+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m:
            effects['change_universe_to'] = m.group(1)
        m = re.search(r"mueve?s?\s+a\s+universo\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m:
            effects['change_universe_to'] = m.group(1)

        # Clean numeric types
        # convert empty dict to {}
        return effects

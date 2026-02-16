#!/usr/bin/env python
from storage import Storage
from ai import AI
import json

try:
    s = Storage('data')
    chars = s.load_characters()
    print(f'Loaded {len(chars)} characters')
    
    univs = s.load_universes()
    print(f'Loaded {len(univs)} universes')
    
    events = s.load_events()
    print(f'Loaded {len(events)} events')
    
    # Test build_system_prompt
    ai = AI()
    if chars and univs:
        char = chars[0]
        univ = univs[0]
        events_sample = events[:3] if events else []
        prompt = ai.build_system_prompt(univ, char, events_sample)
        print(f'\n[PROMPT LENGTH] {len(prompt)} chars')
        print(f'[PROMPT HEAD]\n{prompt[:200]}...\n')
        print('SUCCESS: All functions work!')
    
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()

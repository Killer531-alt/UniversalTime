import requests
import json

BASE = 'http://127.0.0.1:5000'

def test_multiverse():
    r = requests.get(BASE + '/api/multiverse')
    print('multiverse', r.status_code, r.text[:200])

def test_action():
    payload = {
        'student': 'Juan',
        'universe_id': 'u1',
        'character_id': 'ironman_juan',
        'prompt': 'Ataco al villano',
        'class_number': 1
    }
    r = requests.post(BASE + '/api/action', json=payload)
    print('action', r.status_code)
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text)

if __name__ == '__main__':
    test_multiverse()
    test_action()

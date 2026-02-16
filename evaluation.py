def calculate_final_grade(metrics: dict, weights: dict = None) -> dict:
    """Calculate a final grade from metrics using provided weights.

    metrics: keys like 'multiverse', 'universe', 'character', 'life', 'points', 'money', 'hetero', 'auto', 'professor'
    weights: mapping of same keys to percentage weights. If None, use defaults from spec.
    Returns: dict with 'raw_score', 'normalized_score', 'weights_total'
    """
    default_weights = {
        'multiverse': 10,
        'universe': 10,
        'character': 20,
        'life': 10,
        'points': 10,
        'money': 10,
        'hetero': 10,
        'auto': 10,
        'professor': 15,
    }
    w = weights or default_weights
    total_w = sum(w.values())
    raw = 0.0
    for k, wk in w.items():
        val = float(metrics.get(k, 0))
        raw += val * wk
    normalized = raw / total_w if total_w else 0.0
    return {'raw_score': raw, 'normalized_score': normalized, 'weights_total': total_w}

"""Export aggregate results only; never copy protected task text or evaluator traces."""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import random

from appworld_pilot_runner import save


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def analyze(folder):
    plan = json.loads((folder / 'plan.json').read_text(encoding='utf-8'))
    planned = {c['id']: c for c in plan['cells']}
    if len(planned) != len(plan['cells']):
        raise ValueError('Duplicate planned cell IDs')
    rows, missing, partial = [], [], []
    for case_id, cell in planned.items():
        path = folder / 'episodes' / case_id / 'record.json'
        if not path.exists():
            missing.append(case_id)
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        if not record.get('completed'):
            partial.append(case_id)
            continue
        assert record['task_id'] == cell['task_id'] and record['model'] == cell['model']
        assert record['phase'] == 'validation'
        strategy = cell.get('strategy', 'baseline')
        assert record['config'].get('strategy', 'baseline') == strategy
        protocol = cell.get('protocol', 'native')
        assert record['config'].get('protocol', 'native') == protocol
        assert record['experiment_name'] == 'frozen-' + case_id
        for name, value in record['code_hashes'].items():
            assert plan['code_hashes'][name] == value, 'Actor code drift'
        grade = record.get('official_grade', {})
        success = grade.get('result', {}).get('success') if grade.get('ok') else None
        if success is not None and type(success) is not bool:
            raise TypeError('Official success must be boolean')
        rows.append({'id': case_id, 'task_id': cell['task_id'], 'model': cell['model'],
            'repeat': cell['repeat'], 'strategy': strategy, 'protocol': protocol,
            'condition': strategy + '|' + protocol, 'success': success, 'termination': record['termination'],
            'known_tokens': sum(record['usage'].values()), 'usage_complete': record['usage_complete'],
            'model_calls': len(record['responses']), 'tool_calls': len(record['tool_events']),
            'record_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    groups = defaultdict(list)
    for row in rows:
        groups[row['model'] + '|' + row['condition']].append(row)
    by_model = {}
    for model, group in groups.items():
        by_model[model] = {'completed': len(group), 'official_graded': sum(r['success'] is not None for r in group),
            'success': sum(r['success'] is True for r in group),
            'unique_tasks': len({r['task_id'] for r in group}),
            'known_tokens': sum(r['known_tokens'] for r in group),
            'usage_complete': sum(r['usage_complete'] for r in group),
            'termination_counts': dict(Counter(r['termination'] for r in group))}
    # Pair only identical task+repeat across models. Average within task first:
    # repeat count is not treated as the number of independent benchmark tasks.
    models = sorted({c['model'] for c in planned.values()})
    strategies = sorted({c.get('strategy', 'baseline') + '|' + c.get('protocol', 'native') for c in planned.values()})
    contrasts = []
    if len(models) == 2:
        contrasts += [(models[0], s, models[1], s) for s in strategies]
    if len(strategies) == 2:
        contrasts += [(m, strategies[1], m, strategies[0]) for m in models]
    paired = []
    lookup = {(r['task_id'], r['repeat'], r['model'], r['condition']): r for r in rows if r['success'] is not None}
    assert len(lookup) == sum(r['success'] is not None for r in rows), 'Duplicate comparison cell'
    for left_model, left_strategy, right_model, right_strategy in contrasts:
        differences = defaultdict(list)
        for task, repeat in sorted({(r['task_id'], r['repeat']) for r in rows}):
            left = lookup.get((task, repeat, left_model, left_strategy))
            right = lookup.get((task, repeat, right_model, right_strategy))
            if left and right:
                differences[task].append(int(left['success']) - int(right['success']))
        task_means = [sum(v) / len(v) for v in differences.values()]
        comparison = {'difference_direction': f'{left_model}|{left_strategy} minus {right_model}|{right_strategy}',
            'matched_runs': sum(map(len, differences.values())), 'matched_tasks': len(task_means),
            'matched_repeats_by_task': {k: len(v) for k, v in differences.items()}}
        if task_means:
            comparison['task_macro_difference'] = sum(task_means) / len(task_means)
        if len(task_means) >= 2 and len(set(task_means)) == 1:
            comparison['bootstrap_degenerate'] = True
            comparison['uncertainty_note'] = 'Identical observed task differences; a zero-width empirical bootstrap is not evidence of equivalence or zero uncertainty.'
        elif len(task_means) >= 2:
            rng = random.Random(20260920)
            boot = [sum(rng.choices(task_means, k=len(task_means))) / len(task_means) for _ in range(10000)]
            comparison['selected_task_bootstrap_95_interval'] = [percentile(boot, .025), percentile(boot, .975)]
        paired.append(comparison)
    result = {'planned': len(planned), 'completed': len(rows), 'missing': missing, 'partial': partial,
        'plan_sha256': hashlib.sha256((folder / 'plan.json').read_bytes()).hexdigest(),
        'models': by_model, 'paired': paired, 'cells': rows,
        'boundary': 'Fixed selected-task subset, structured API actor, AWQ weights. Bootstrap describes sensitivity to selected task composition, not population significance. Repeats are correlated. Missing and ungraded counts remain explicit. No protected task text or evaluator traces exported.'}
    save(folder / 'aggregate-analysis.json', result)
    print(json.dumps({k: result[k] for k in ['planned', 'completed', 'models', 'paired']}))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', type=Path, required=True)
    analyze(p.parse_args().folder)

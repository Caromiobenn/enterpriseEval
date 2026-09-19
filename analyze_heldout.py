"""Post-review analysis. Refuses grading without a complete blind-label artifact."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import deepseek_study as study


def replay(record):
    cell = record['cell']
    case = study.scenario(cell['family'], cell['variant'])
    assert record['initial'] == case['initial'], 'initial state mismatch'
    assistant_messages = [m for m in record['messages'] if m['role'] == 'assistant']
    raw_messages = [r['raw']['choices'][0]['message'] for r in record['responses']]
    assert assistant_messages == raw_messages, 'raw/model transcript mismatch'
    env = study.Environment(case, cell['fault'])
    pending = {}
    for message in record['messages']:
        if message['role'] == 'assistant':
            for call in message.get('tool_calls') or []:
                pending[call['id']] = call['function']
        elif message['role'] == 'tool':
            call = pending.pop(message['tool_call_id'])
            observed = env.call(call['name'], json.loads(call['arguments']))
            assert observed == json.loads(message['content']), 'tool response mismatch'
    assert env.state == record['final'], 'final state mismatch'
    assert env.effects == record['effects'], 'effect journal mismatch'
    assert env.events == record['events'], 'event journal mismatch'
    assert env.exposed == record['fault_exposed'], 'fault exposure mismatch'
    return case


def analyze(folder, labels_path):
    labels_data = json.loads(labels_path.read_text(encoding='utf-8'))
    mapping = json.loads((folder / 'blind-mapping-private.json').read_text())
    assert mapping, 'no blinded records available'
    labels = {entry['blind_id']: entry for entry in labels_data['labels']}
    assert len(labels) == len(labels_data['labels']), 'duplicate blind label'
    assert set(labels) == set(mapping), 'incomplete blind labels'
    assert labels_data['reviewer'] == 'Codex model; not independent human gold'
    for label in labels.values():
        assert label['evidence'] and isinstance(label['success'], bool)
    plan = json.loads((folder / 'plan.json').read_text())
    planned = {c['id']: c for c in plan['cells']}
    records, groups, comparisons, disagreements = {}, defaultdict(list), defaultdict(dict), []
    for path in sorted((folder / 'records').glob('*.json')):
        record = json.loads(path.read_text())
        cell = record['cell']
        assert cell['id'] == path.stem and planned[cell['id']] == cell
        if not record.get('completed') or cell['split'] != 'validation':
            continue
        case = replay(record)
        result = study.grade(case, record['final'], record['effects'])
        tokens = 0
        usage_complete = True
        for response in record['responses']:
            u = response['raw'].get('usage') or {}
            if isinstance(u.get('total_tokens'), int):
                tokens += u['total_tokens']
            else:
                usage_complete = False
        row = {'id': cell['id'], 'success': result['success'], 'checks': result['checks'],
               'termination': record['termination'], 'fault_exposed': record['fault_exposed'],
               'known_tokens': tokens, 'usage_complete': usage_complete,
               'model_calls': len(record['responses']), 'tool_calls': len(record['events'])}
        records[cell['id']] = row
        groups[(cell['model'], cell['family'], cell['strategy'], cell['fault'])].append(row)
        comparisons[(cell['model'], cell['family'], cell['variant'], cell['repeat'], cell['fault'])][cell['strategy']] = row
    for blind_id, case_id in mapping.items():
        assert case_id in records
        if labels[blind_id]['success'] != records[case_id]['success']:
            disagreements.append({'blind_id': blind_id, 'id': case_id,
                'blind_success': labels[blind_id]['success'], 'grader': records[case_id]})
    summaries = []
    for key, rows in sorted(groups.items()):
        summaries.append(dict(zip(['model', 'family', 'strategy', 'fault'], key)) | {
            'n': len(rows), 'success': sum(r['success'] for r in rows),
            'fault_exposed': sum(r['fault_exposed'] for r in rows),
            'known_tokens': sum(r['known_tokens'] for r in rows),
            'usage_complete': sum(r['usage_complete'] for r in rows),
            'terminations': dict(Counter(r['termination'] for r in rows))})
    paired = []
    for key, options in sorted(comparisons.items()):
        if set(options) != {'minimal', 'recovery'}:
            continue
        paired.append(dict(zip(['model', 'family', 'variant', 'repeat', 'fault'], key)) | {
            'minimal': options['minimal']['success'], 'recovery': options['recovery']['success']})
    result = {'label_file_sha256': hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        'plan_sha256': hashlib.sha256((folder / 'plan.json').read_bytes()).hexdigest(),
        'validation_completed': len(records),
        'validation_planned': sum(c['split'] == 'validation' for c in planned.values()),
        'missing_validation_ids': [c['id'] for c in planned.values() if c['split'] == 'validation' and c['id'] not in records],
        'replay_exact': len(records), 'blind_review_n': len(labels), 'disagreements': disagreements,
        'groups': summaries, 'prompt_pairs': paired, 'records': records,
        'inference_boundary': 'Two synthetic semantic families. Variants/repeats correlated. No population significance claim.'}
    study.save(folder / 'postreview-analysis.json', result)
    print(json.dumps({k: result[k] for k in ['validation_completed', 'validation_planned', 'replay_exact', 'blind_review_n']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--blind-labels', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.folder, args.blind_labels)

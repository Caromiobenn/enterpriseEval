"""Secondary process-compliance audit; never changes the frozen primary score.

Operationalizes 'read current state and verify final result' as an initial
observation before any accepted write and a final observation after all accepted
writes. Reports its deliberately stricter temporal definition separately.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def observation_checks(record):
    events = record['events']
    reads = [i for i, e in enumerate(events) if e['name'] == 'read_state']
    writes = [i for i, e in enumerate(events) if e['name'] != 'read_state' and
              (e['response'].get('ok') is True or e['response'].get('error') == 'response_timeout')]
    return {
        'initial_observed_before_writes': bool(reads) and (not writes or reads[0] < writes[0])
            and events[reads[0]]['response'] == record['initial'],
        'final_observed_after_writes': bool(reads) and (not writes or reads[-1] > writes[-1])
            and events[reads[-1]]['response'] == record['final']}


def audit(folder):
    rows = []
    for path in sorted((folder / 'records').glob('*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['cell']['split'] != 'validation' or not record.get('completed'):
            continue
        rows.append({'id': path.stem, **observation_checks(record)})
    result = {'validation_completed': len(rows),
        'jointly_satisfied': sum(all(r[k] for k in ['initial_observed_before_writes', 'final_observed_after_writes']) for r in rows),
        'counts': dict(Counter(k for r in rows for k in ['initial_observed_before_writes', 'final_observed_after_writes'] if r[k])),
        'records': rows, 'primary_grade_changed': False,
        'limitation': 'Post-hoc secondary audit. Frozen primary state/unique-commit grader does not check read/verification obligations. This audit is automated and not independent human gold.'}
    (folder / 'observation-audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['validation_completed', 'jointly_satisfied', 'counts']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', type=Path, required=True)
    audit(p.parse_args().folder)

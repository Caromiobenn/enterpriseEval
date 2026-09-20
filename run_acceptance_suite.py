"""Compare separate model adjudications with deterministic grader outputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from acceptance_grader import evaluate
from deepseek_study import grade


def run(folder, output):
    if output.exists():
        raise ValueError('Refusing to overwrite a previous acceptance report')
    load = lambda name: json.loads((folder / name).read_text(encoding='utf-8'))
    for name, digest in load('fixture-hashes.json').items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Fixture hash mismatch: ' + name)
    samples = load('samples.json')
    labels = load('model-adjudications.json')
    expected = {x['id']: x for x in labels['judgments']}
    if len(expected) != len(samples) or {s['id'] for s in samples} != set(expected):
        raise ValueError('Missing, duplicate or unexpected fixture IDs')
    rows = []
    for sample in samples:
        # Grader never receives expected labels, category or review rationale.
        result = evaluate(sample['task'], sample['artifact'])
        label = expected[sample['id']]
        legacy = grade(sample['task']['case'], sample['artifact']['final'], sample['artifact']['effects'])
        rows.append({'id': sample['id'], 'category': label['category'], 'expected': label['expected_verdict'],
                     'actual': result, 'legacy_primary_success': legacy['success'],
                     'agrees': result['verdict'] == label['expected_verdict']})
    report = {'samples': len(rows), 'agreement': sum(r['agrees'] for r in rows),
              'verdict_counts': dict(Counter(r['actual']['verdict'] for r in rows)),
              'reviewer': labels['reviewer'], 'rows': rows,
              'limits': 'Constructed calibration fixtures, not model episodes, independent human gold, or estimates of real-world grader accuracy.',
              'code_hashes': {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                              for n in ['acceptance_grader.py', 'run_acceptance_suite.py', 'deepseek_study.py']}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['samples', 'agreement', 'verdict_counts']}))
    if report['agreement'] != report['samples']:
        raise SystemExit('Acceptance disagreement; inspect report, do not silently change labels')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.folder, args.output)

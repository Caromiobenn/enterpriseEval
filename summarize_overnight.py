"""Summarize sanitized campaign evidence; no model calls or protected task content."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean


def summarize(root):
    audit = root / 'final-audit'
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    result = {'date': '2026-09-20', 'synthetic': {}, 'external': {}}
    for name, folder in [('api', 'deepseek-heldout-authfixed-20260919'), ('local', 'local-heldout-20260919')]:
        report = load(root / folder / 'postreview-analysis.json')
        assert report['validation_completed'] == report['replay_exact']
        assert not report['missing_validation_ids']
        result['synthetic'][name] = {k: report[k] for k in ['validation_completed', 'validation_planned', 'replay_exact', 'blind_review_n', 'disagreements', 'groups', 'label_file_sha256', 'plan_sha256']}
    all_prefixes = set()
    for version in ['v8', 'v9', 'v10']:
        report = load(audit / f'{version}-aggregate.json')
        plan = load(audit / f'{version}-plan.json')
        assert hashlib.sha256((audit / f'{version}-plan.json').read_bytes()).hexdigest() == report['plan_sha256']
        prefixes = {r['task_id'].split('_')[0] for r in report['cells']}
        assert not prefixes & all_prefixes
        all_prefixes |= prefixes
        assert report['planned'] == report['completed'] + len(report['missing']) + len(report['partial'])
        processes = load(audit / f'{version}-processes.json')
        assert len(processes) == report['completed']
        assert all(r.get('returncode') == 0 for r in processes)
        out = {k: report[k] for k in ['planned', 'completed', 'models', 'paired', 'plan_sha256']}
        out.update(missing=len(report['missing']), partial=len(report['partial']),
                   unique_prefixes=len(prefixes), started_utc=min(r['started_utc'] for r in processes),
                   ended_utc=max(r['ended_utc'] for r in processes))
        out['protocol_diagnostics_matched'] = {}
        for model in sorted({r['model'] for r in report['cells']}):
            rows = [r for r in report['cells'] if r['model'] == model]
            lookup = {(r['task_id'], r['repeat'], r['protocol']): r for r in rows}
            pairs = [(r, lookup[(r['task_id'], r['repeat'], 'constrained_json')]) for r in rows
                     if r['protocol'] == 'native' and (r['task_id'], r['repeat'], 'constrained_json') in lookup]
            if pairs:
                out['protocol_diagnostics_matched'][model] = {'pairs': len(pairs), **{
                    protocol: {'truncated': sum(pair[i]['termination'] == 'output_truncated' for pair in pairs),
                               'known_tokens': sum(pair[i]['known_tokens'] for pair in pairs),
                               'model_calls': sum(pair[i]['model_calls'] for pair in pairs)}
                    for i, protocol in enumerate(['native', 'constrained_json'])}}
        result['external'][version] = out
    result['external_unique_prefixes'] = len(all_prefixes)
    result['new_validation_runs'] = sum(x['validation_completed'] for x in result['synthetic'].values()) + sum(x['completed'] for x in result['external'].values())
    telemetry = list(csv.DictReader((audit / 'gpu-telemetry.csv').open(encoding='utf-8')))
    result['telemetry'] = {'first_server_local': telemetry[0]['timestamp'], 'last_server_local': telemetry[-1]['timestamp'],
        'limitation': 'Telemetry stops at 01:01; do not extrapolate utilization to the whole campaign.', 'gpus': {}}
    for gpu in ['0', '1']:
        values = [float(r[' utilization.gpu [%]'].strip().split()[0]) for r in telemetry if r[' index'].strip() == gpu]
        result['telemetry']['gpus'][gpu] = {'samples': len(values), 'mean_percent': mean(values)}
    owned = load(audit / 'owned-processes.json')
    start = next(r['created'] for r in owned if r['pid'] == 31276)
    end = datetime.fromisoformat(result['external']['v10']['ended_utc']).timestamp()
    result['execution_span'] = {'start_process_utc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
        'last_episode_utc': result['external']['v10']['ended_utc'], 'hours': (end-start)/3600,
        'limitation': 'Elapsed batch span, not cumulative GPU busy time; contains setup and inter-episode gaps.'}
    result['deadline_stop'] = load(audit / 'deadline-stop.json')
    assert all(r.get('stopped') or r.get('already_exited') for r in result['deadline_stop'])
    (audit / 'campaign-summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'validation_runs': result['new_validation_runs'], 'external_prefixes': len(all_prefixes), 'elapsed_hours': result['execution_span']['hours']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    summarize(parser.parse_args().root)

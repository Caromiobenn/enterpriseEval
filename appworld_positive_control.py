"""Replay official TRAIN reference HTTP logs through the structured bridge.

Run only after private official reference controls generated their logs. Never
use held-out reference solutions. Outputs contain aggregate control results only.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, unquote

from appworld_pilot_runner import Bridge, save


def main(root):
    from appworld.task import Task
    from appworld import load_task_ids
    selection = json.loads((root / 'selection.json').read_text())
    train = set(load_task_ids('train'))
    results = []
    for index, task_id in enumerate(selection['development_ids']):
        assert task_id in train
        task = Task.load(task_id, load_ground_truth=False)
        docs = [doc for apis in task.api_docs.values() for doc in apis.values()]
        log = root / 'experiments' / 'outputs' / f'positive-control-train-{index}' / 'tasks' / task_id / 'logs' / 'api_calls.jsonl'
        calls = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        bridge = Bridge(sys.executable, root, root / f'bridge-control-{index}-stderr.log')
        row = {'task_id': task_id, 'source': 'official train reference request log', 'replayed_calls': 0}
        try:
            assert bridge.send({'op': 'initialize', 'task_id': task_id,
                                'experiment_name': f'bridge-positive-control-{index}'})['ok']
            for call in calls:
                path = urlsplit(call['url']).path
                matches = []
                for doc in docs:
                    if doc['method'].lower() != call['method'].lower():
                        continue
                    pattern = re.sub(r'\\\{(\w+)\\\}', r'(?P<\1>[^/]+)', re.escape(doc['path']))
                    match = re.fullmatch(pattern, path)
                    if match:
                        matches.append((doc, match.groupdict()))
                if len(matches) != 1:
                    raise ValueError('Reference request did not map to one public API')
                doc, route = matches[0]
                arguments = dict(call['data'])
                arguments.update({k: int(v) if v.isdigit() else unquote(v) for k, v in route.items()})
                response = bridge.send({'op': 'tool', 'name': 'call_api', 'arguments': {
                    'app': doc['app_name'], 'api': doc['api_name'], 'arguments': arguments}})
                if not response.get('ok'):
                    raise RuntimeError(response.get('error_type', 'Bridge error'))
                row['replayed_calls'] += 1
            grade = bridge.send({'op': 'finish_and_grade'})
            row['official_grade_available'] = grade.get('ok')
            row['success'] = grade.get('result', {}).get('success')
        except Exception as exc:
            row['error_type'] = type(exc).__name__
            row['error'] = str(exc)
        finally:
            bridge.close()
        results.append(row)
    save(root / 'bridge-positive-controls-summary.json', results)
    print(json.dumps(results))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    main(p.parse_args().root.resolve())

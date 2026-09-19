"""Select official split task IDs without looking at task text, solutions or scores."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


def select_ids(ids, count):
    chosen, templates = [], set()
    for task_id in sorted(ids, key=lambda x: hashlib.sha256(('20260920:' + x).encode()).hexdigest()):
        template = task_id.rsplit('_', 1)[0]
        if template in templates:
            continue
        chosen.append(task_id)
        templates.add(template)
        if len(chosen) == count:
            break
    if len(chosen) != count:
        raise ValueError('Insufficient distinct task prefixes; inspect official ID convention before proceeding')
    return chosen


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--validation-count', type=int, default=16)
    args = p.parse_args()
    if args.output.exists():
        raise RuntimeError('Refusing to overwrite frozen selection')
    from appworld import load_task_ids
    train = list(load_task_ids('train'))
    test = list(load_task_ids('test_normal'))
    assert not set(train) & set(test)
    result = {'appworld_version': importlib.metadata.version('appworld'),
              'selection': 'SHA256(20260920:task_id), first unique underscore prefix; no model-result selection',
              'development_split': 'train', 'development_ids': select_ids(train, 2),
              'validation_split': 'test_normal', 'validation_ids': select_ids(test, args.validation_count),
              'split_id_hashes': {name: hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()
                                 for name, ids in [('train', train), ('test_normal', test)]},
              'status': 'selection only; actor configuration must be frozen after development before validation'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'development_tasks': 2, 'validation_tasks': len(result['validation_ids']),
                      'package_version': result['appworld_version']}))

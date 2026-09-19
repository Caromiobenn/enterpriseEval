"""Two GPU workers, frozen business tools shared with API study, no API secrets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import time
import urllib.request

import deepseek_study as study

MODELS = {'qwen2.5-14b-instruct-awq': 8066, 'qwen2.5-7b-instruct-awq': 8067}


class LocalClient:
    def __init__(self, model, folder, deadline):
        self.model, self.folder, self.deadline = model, folder, deadline
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.ledger = {'calls': 0, 'tokens': 0, 'provider': 'local_vllm', 'usage_complete': True}

    def send(self, payload):
        if time.time() >= self.deadline:
            raise study.BudgetStop('overnight deadline')
        payload = dict(payload)
        payload.pop('thinking', None)  # Local model is non-thinking; API-only parameter.
        request = urllib.request.Request(f'http://127.0.0.1:{MODELS[self.model]}/v1/chat/completions',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        started = time.monotonic()
        with self.opener.open(request, timeout=120) as response:
            output = json.load(response)
        self.ledger['calls'] += 1
        usage = output.get('usage') or {}
        if isinstance(usage.get('total_tokens'), int):
            self.ledger['tokens'] += usage['total_tokens']
        else:
            self.ledger['usage_complete'] = False
        study.save(self.folder / ('usage-' + self.model + '.json'), self.ledger)
        return output, round(time.monotonic() - started, 3)


def code_hashes():
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ['local_heldout_study.py', 'deepseek_study.py', 'workflows.py']}


def create(folder):
    if folder.exists():
        raise RuntimeError('existing output folder')
    cells = []
    for model in MODELS:
        for strategy in ['minimal', 'recovery']:
            cells.append(dict(split='development', family='offboarding', variant=4401,
                              model=model, strategy=strategy, fault=True, repeat=0))
    validation = []
    for model in MODELS:
        for family in ['release', 'fulfillment']:
            for variant in range(4):
                for strategy in ['minimal', 'recovery']:
                    for fault in [False, True]:
                        for repeat in range(8):
                            validation.append(dict(split='validation', family=family, variant=variant,
                                model=model, strategy=strategy, fault=fault, repeat=repeat))
    random.Random(918271).shuffle(validation)
    cells += validation
    for cell in cells:
        cell['id'] = study.sha(cell)[:20]
    study.save(folder / 'plan.json', {'cells': cells, 'hashes': code_hashes(), 'selftests': study.selftest(),
        'models': MODELS, 'repeats_per_condition': 8, 'validation_cells': len(validation),
        'comparability': 'same tasks/tools/prompts/temperature/output cap as API; provider and weights differ',
        'no_seed_claim': True, 'holdout_grades_deferred': True,
        'deadline_utc': '2026-09-20T01:00:00+00:00'})
    print(json.dumps({'total': len(cells), 'validation': len(validation)}))


def run(folder):
    from datetime import datetime
    plan = json.loads((folder / 'plan.json').read_text())
    assert plan['hashes'] == code_hashes(), 'source changed after freeze'
    deadline = datetime.fromisoformat(plan['deadline_utc']).timestamp()
    def worker(model):
        client = LocalClient(model, folder, deadline)
        for cell in [c for c in plan['cells'] if c['model'] == model]:
            path = folder / 'records' / (cell['id'] + '.json')
            if path.exists():
                record = json.loads(path.read_text())
                if not record.get('completed'):
                    raise RuntimeError('incomplete cell requires audit')
                continue
            if time.time() >= deadline:
                break
            ending = study.run_episode(cell, client, folder)
            print(json.dumps({'id': cell['id'], 'model': model, 'split': cell['split'], 'termination': ending}), flush=True)
            if ending == 'budget_stop':
                break
            # Stop development transport/protocol failure before touching validation.
            if cell['split'] == 'development' and ending == 'execution_error':
                break
        return model
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, MODELS))
    study.blind_export(folder, plan)
    records = [json.loads(p.read_text()) for p in (folder / 'records').glob('*.json')]
    study.save(folder / 'status.json', {'planned': len(plan['cells']),
        'completed': sum(r.get('completed', False) for r in records), 'blind_review_pending': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'run'])
    parser.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args()
    create(args.folder) if args.command == 'plan' else run(args.folder)

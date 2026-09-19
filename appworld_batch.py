"""Frozen, deadline-bounded local AppWorld validation; keep output server-private."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

from appworld_pilot_runner import save

MODELS = {'qwen2.5-7b-instruct-awq': 'http://127.0.0.1:8067/v1',
          'qwen2.5-14b-instruct-awq': 'http://127.0.0.1:8066/v1'}


def hashes():
    return {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
            for n in ['appworld_batch.py', 'appworld_pilot_runner.py', 'appworld_tool_bridge.py']}


def plan(args):
    if args.output.exists():
        raise ValueError('Refusing to overwrite existing batch')
    selection = json.loads(args.selection.read_text(encoding='utf-8'))
    tasks = selection['validation_ids']
    assert not set(tasks) & set(selection['development_ids'])
    cells = []
    for repeat in range(8):
        order = list(tasks)
        random.Random(20260920 + repeat).shuffle(order)
        for task in order:
            for model, url in MODELS.items():
                strategies = ['baseline', 'discovery_guidance']
                random.Random(f'{repeat}:{task}:{model}').shuffle(strategies)
                for strategy in strategies:
                    cell = dict(task_id=task, model=model, base_url=url, repeat=repeat, strategy=strategy)
                    cell['id'] = hashlib.sha256(json.dumps(cell, sort_keys=True).encode()).hexdigest()[:20]
                    cells.append(cell)
    args.output.mkdir(parents=True)
    save(args.output / 'plan.json', {'cells': cells, 'code_hashes': hashes(),
        'selection_sha256': hashlib.sha256(args.selection.read_bytes()).hexdigest(),
        'selection': selection, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'deadline_utc': '2026-09-20T01:00:00+00:00',
        'repeats': 8, 'episode_timeout_seconds': 1200,
        'purpose': 'On disjoint task prefixes, test discovery-guidance prompt only; same tools, model, decoding and episode caps. Match within task/model/repeat. Equal caps, not equal realized token cost.',
        'limits': 'Structured API actor, not official code-agent baseline. AWQ local models. Repeats not independent semantic tasks. Incomplete cells retained; no score-dependent selection.'})
    print(json.dumps({'planned': len(cells), 'unique_tasks': len(tasks)}))


def run(args):
    frozen = json.loads((args.output / 'plan.json').read_text(encoding='utf-8'))
    assert hashes() == frozen['code_hashes'], 'Code changed after freeze'
    deadline = datetime.fromisoformat(frozen['deadline_utc']).timestamp()
    def worker(model):
        for cell in (c for c in frozen['cells'] if c['model'] == model):
            out = args.output / 'episodes' / cell['id']
            record = out / 'record.json'
            if out.exists():
                if not record.exists() or not json.loads(record.read_text()).get('completed'):
                    raise RuntimeError('Unresolved partial episode; do not silently retry')
                continue
            remaining = deadline - time.time()
            if remaining < 60:
                break
            out.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, str(Path(__file__).with_name('appworld_pilot_runner.py')),
                '--task-id', cell['task_id'], '--model', model, '--base-url', cell['base_url'],
                '--root', str(args.root.resolve()), '--output', str(out.resolve()),
                '--experiment', 'frozen-' + cell['id'], '--phase', 'validation', '--strategy', cell['strategy']]
            started = datetime.now(timezone.utc).isoformat()
            with (out.parent / (cell['id'] + '.log')).open('w') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                try:
                    status = {'returncode': process.wait(timeout=min(1200, remaining))}
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    status = {'timeout': True}
            save(out.parent / (cell['id'] + '-process.json'),
                 dict(status, id=cell['id'], started_utc=started,
                      ended_utc=datetime.now(timezone.utc).isoformat()))
            print(json.dumps(dict(id=cell['id'], model=model, **status)), flush=True)
            # Infrastructure failure stops this model queue rather than generating
            # a large batch of identical invalid episodes.
            if status.get('returncode') != 0 or not record.exists():
                break
            outcome = json.loads(record.read_text())
            if outcome.get('termination') == 'execution_error' or not outcome.get('official_grade', {}).get('ok'):
                break
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, MODELS))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['plan', 'run'])
    p.add_argument('--selection', type=Path)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    plan(args) if args.command == 'plan' else run(args)

"""Frozen live-rollout intervention study; no API keys or evaluator-state policy access.

The two synthetic contracts explicitly authorize each business operation once.
namespace separates different operations sharing a model ID; semantic additionally
deduplicates the same operation across different model IDs. Neither uses outcomes.
"""
import argparse
import copy
import hashlib
import json
import math
import random
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import deepseek_study as base

MODELS = {'qwen2.5-14b-instruct-awq': 8066, 'qwen2.5-7b-instruct-awq': 8067}
ARMS = ['raw', 'namespace', 'semantic']
SOURCE_FILES = ['recovery_study.py', 'deepseek_study.py', 'workflows.py']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def hashes():
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def make_case(family, variant, size):
    case = base.scenario(family, variant)
    rng = random.Random(variant)
    ids = [f'{family}-{variant}-item-{i}' for i in range(size)]
    rng.shuffle(ids)
    if family == 'release':
        case['initial']['components'] = {i: {'security': False, 'owner': False, 'deployed': False} for i in ids}
        case['instruction'] = case['instruction'].replace('three components', f'{size} components')
    else:
        orders = {oid: {'sku': f'sku-{i % 2}', 'quantity': rng.randint(1, 3), 'reserved': False, 'shipped': False}
                  for i, oid in enumerate(ids)}
        stock = {sku: sum(o['quantity'] for o in orders.values() if o['sku'] == sku) + rng.randint(3, 7)
                 for sku in ['sku-0', 'sku-1']}
        case['initial'].update(orders=orders, stock=stock)
        case['instruction'] = case['instruction'].replace('three orders', f'{size} orders')
    case['size'] = size
    return case


class RequestPolicy:
    """Only public tool schema, raw call, and an explicit once-only contract are used."""
    def __init__(self, arm, tools, once_only):
        if arm not in ARMS:
            raise ValueError(arm)
        self.arm = arm
        self.schemas = {x['function']['name']: x['function']['parameters'] for x in tools}
        self.once_only = set(once_only)

    def transform(self, name, args):
        result = copy.deepcopy(args)
        if self.arm == 'raw' or name not in self.once_only or not isinstance(args, dict):
            return result
        schema = self.schemas.get(name)
        if not schema or set(args) != set(schema['required']) or not all(isinstance(v, str) for v in args.values()):
            return result  # Never repair malformed arguments or unauthorized operations.
        semantic = {'tool': name, 'parameters': {k: v for k, v in args.items() if k != 'request_id'}}
        key = semantic if self.arm == 'semantic' else {'semantic': semantic, 'model_request_id': args['request_id']}
        result['request_id'] = 'exec-' + digest(key)  # Task-local environment scopes this namespace.
        return result


def prompt(strategy):
    value = 'Complete the task using tools. Read the initial state and verify the final state before finishing.'
    if strategy == 'recovery':
        value += ' After a write timeout inspect state or retry exactly the same operation with the same request_id. Never issue a new write ID for an operation already committed. Track distinct operation IDs.'
    return value


def create_plan(folder, phase, hours, inventory):
    if folder.exists():
        raise RuntimeError('Refusing to overwrite an existing study')
    pilot = phase == 'pilot'
    cells = []
    for model in MODELS:
        for family in ['release', 'fulfillment']:
            for fault in [False, True]:
                for size in ([3] if pilot else [3, 5]):
                    for variant in ([81001] if pilot else [91001, 91002, 91003, 91004]):
                        for strategy in (['minimal'] if pilot else ['minimal', 'recovery']):
                            for repeat in range(1 if pilot else 4):
                                for arm in ARMS:
                                    cell = dict(model=model, family=family, fault=fault, size=size,
                                                variant=variant, strategy=strategy, repeat=repeat, arm=arm, phase=phase)
                                    cell['id'] = digest(cell)[:24]
                                    cells.append(cell)
    random.Random(20261016).shuffle(cells)
    created = datetime.now(timezone.utc)
    plan = {'version': 'live-recovery-v1', 'created_utc': created.isoformat(),
            'deadline_utc': datetime.fromtimestamp(created.timestamp() + hours * 3600, timezone.utc).isoformat(),
            'phase': phase, 'cells': cells, 'code_sha256': hashes(), 'models': MODELS,
            'model_inventory': json.loads(inventory.read_text()) if inventory else None,
            'max_model_calls': 24, 'max_output_tokens': 1024, 'temperature': 0.2,
            'primary': 'Complete state and no duplicate committed operation; all started episodes retained',
            'secondary': ['observation obligations', 'duplicate commits', 'request conflicts', 'fault exposure', 'tokens', 'termination'],
            'comparison': 'semantic vs raw primary; namespace vs raw and semantic vs namespace mechanistic ablations',
            'limitations': ['Two synthetic semantic families, not production traffic or new semantic domains',
                            'Task size and numeric/identifier variants provide limited structural transfer',
                            'No coupled random-number or identical-generation seed claim',
                            'Policies apply only to explicit once-only business contracts',
                            'Earlier 640 trajectories and pilot are development, never pooled with validation'],
            'inference': 'Report paired cell transitions; cluster by family, size and variant; two-family generalization is not established',
            'stop_rules': ['deadline', 'positive control failure', 'code drift', 'three transport/protocol failures in pilot'],
            'positive_controls': positive_controls()}
    base.save(folder / 'plan.json', plan)
    print(json.dumps({'phase': phase, 'planned': len(cells), 'deadline_utc': plan['deadline_utc']}))


def positive_controls():
    checks = []
    for family in ['release', 'fulfillment']:
        for size in [3, 5]:
            for fault in [False, True]:
                case = make_case(family, 81001, size)
                for reverse in [False, True]:
                    env = base.reference(case, reverse, fault)
                    assert base.grade(case, env.state, env.effects)['success']
                    checks.append([family, size, fault, reverse])
    return checks


def run_episode(cell, plan, folder):
    case = make_case(cell['family'], cell['variant'], cell['size'])
    env = base.Environment(case, cell['fault'])
    tools = env.specs()
    once_only = [t['function']['name'] for t in tools if t['function']['name'] != 'read_state']
    policy = RequestPolicy(cell['arm'], tools, once_only)
    messages = [{'role': 'system', 'content': prompt(cell['strategy'])},
                {'role': 'user', 'content': json.dumps({'instruction': case['instruction']})}]
    record = {'cell': cell, 'case': case, 'messages': messages, 'responses': [], 'mappings': [],
              'termination': 'model_call_limit', 'completed': False, 'started_utc': datetime.now(timezone.utc).isoformat()}
    target = folder / 'records' / (cell['id'] + '.json')
    if target.exists():
        raise RuntimeError('Existing episode; refusing overwrite')
    base.save(target, record)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = datetime.fromisoformat(plan['deadline_utc']).timestamp()
    try:
        for turn in range(plan['max_model_calls']):
            if time.time() >= deadline:
                record['termination'] = 'budget_stop'
                break
            payload = {'model': cell['model'], 'messages': messages, 'tools': tools,
                       'temperature': plan['temperature'], 'max_tokens': plan['max_output_tokens'], 'stream': False}
            request = urllib.request.Request(f'http://127.0.0.1:{MODELS[cell["model"]]}/v1/chat/completions',
                      data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            start = time.monotonic()
            with opener.open(request, timeout=min(180, max(1, deadline - time.time()))) as response:
                output = json.load(response)
            record['responses'].append({'raw': output, 'seconds': round(time.monotonic() - start, 4)})
            choice = output['choices'][0]
            msg = choice['message']
            messages.append(msg)
            if choice.get('finish_reason') == 'length':
                record['termination'] = 'output_truncated'
                break
            calls = msg.get('tool_calls') or []
            if not calls:
                record['termination'] = 'actor_finished'
                break
            for call in calls:
                name = call['function']['name']
                args = json.loads(call['function']['arguments'])
                effective = policy.transform(name, args)
                result = env.call(name, effective)
                record['mappings'].append({'turn': turn, 'tool_call_id': call['id'], 'name': name,
                                           'raw_arguments': args, 'effective_arguments': effective})
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
            base.save(target, record)
    except Exception as exc:
        record['termination'] = 'execution_error'
        record['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
    record.update(final=env.state, effects=env.effects, events=env.events, fault_exposed=env.exposed,
                  completed=True, ended_utc=datetime.now(timezone.utc).isoformat())
    base.save(target, record)
    return record


def replay(record):
    cell = record['cell']
    case = make_case(cell['family'], cell['variant'], cell['size'])
    assert case == record['case'], 'Case drift'
    env = base.Environment(case, cell['fault'])
    tools = env.specs()
    policy = RequestPolicy(cell['arm'], tools, [t['function']['name'] for t in tools if t['function']['name'] != 'read_state'])
    expected_messages = [{'role': 'system', 'content': prompt(cell['strategy'])},
                         {'role': 'user', 'content': json.dumps({'instruction': case['instruction']})}]
    mapping_index = 0
    commits, reads = [], []
    for turn, response in enumerate(record['responses']):
        choice = response['raw']['choices'][0]
        msg = choice['message']
        expected_messages.append(msg)
        if choice.get('finish_reason') == 'length':
            break
        for call in msg.get('tool_calls') or []:
            # An incomplete/malformed call can end an execution_error episode before execution.
            try:
                args = json.loads(call['function']['arguments'])
            except (ValueError, TypeError):
                assert record['termination'] == 'execution_error'
                break
            name = call['function']['name']
            effective = policy.transform(name, args)
            assert record['mappings'][mapping_index] == {'turn': turn, 'tool_call_id': call['id'], 'name': name,
                    'raw_arguments': args, 'effective_arguments': effective}, 'Mapping mismatch'
            prior = len(env.effects)
            result = env.call(name, effective)
            if len(env.effects) > prior:
                commits.append(mapping_index)
            if name == 'read_state':
                reads.append((mapping_index, copy.deepcopy(result)))
            expected_messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
            mapping_index += 1
    assert expected_messages == record['messages'], 'Raw response and actor transcript mismatch'
    assert mapping_index == len(record['mappings']), 'Unexpected mapping'
    assert env.events == record['events'] and env.effects == record['effects'], 'Event mismatch'
    assert env.state == record['final'] and env.exposed == record['fault_exposed'], 'State/fault mismatch'
    result = base.grade(case, env.state, env.effects)
    observed = any(v == case['initial'] and (not commits or i < commits[0]) for i, v in reads) and \
               any(v == env.state and (not commits or i > commits[-1]) for i, v in reads)
    return result, observed


def summarize(folder):
    plan = json.loads((folder / 'plan.json').read_text())
    assert plan['code_sha256'] == hashes(), 'Source changed after plan freeze'
    rows, missing, incomplete = [], [], []
    for cell in plan['cells']:
        path = folder / 'records' / (cell['id'] + '.json')
        if not path.exists():
            missing.append(cell['id'])
            continue
        record = json.loads(path.read_text())
        if not record.get('completed'):
            incomplete.append(cell['id'])
            continue
        result, observed = replay(record)
        tokens = [r['raw'].get('usage', {}).get('total_tokens') for r in record['responses']]
        errors = Counter(e['response'].get('error') for e in record['events'] if isinstance(e['response'], dict) and e['response'].get('error'))
        row = dict(cell, success=result['success'], strict_success=result['success'] and observed,
                   full_state=result['checks']['full_state'], duplicate=not result['checks']['no_duplicate_committed_operation'],
                   observed=observed, fault_exposed=record['fault_exposed'], termination=record['termination'],
                   request_id_conflicts=errors['request_id_conflict'], model_calls=len(tokens),
                   tokens=sum(t for t in tokens if isinstance(t, int)), usage_complete=all(isinstance(t, int) for t in tokens),
                   seconds=sum(r['seconds'] for r in record['responses']))
        rows.append(row)
    groups = defaultdict(list)
    for row in rows:
        groups['|'.join(str(row[k]) for k in ['model', 'arm', 'strategy', 'family', 'size', 'fault'])].append(row)
    metrics = {k: {'n': len(v), 'success': sum(x['success'] for x in v), 'strict_success': sum(x['strict_success'] for x in v),
                   'duplicates': sum(x['duplicate'] for x in v), 'conflict_episodes': sum(x['request_id_conflicts'] > 0 for x in v),
                   'tokens': sum(x['tokens'] for x in v), 'terminations': dict(Counter(x['termination'] for x in v))} for k, v in groups.items()}
    pairs = defaultdict(dict)
    for row in rows:
        key = tuple(row[k] for k in ['model', 'family', 'size', 'variant', 'strategy', 'fault', 'repeat'])
        pairs[key][row['arm']] = row
    transitions = {}
    for a, b in [('raw', 'semantic'), ('raw', 'namespace'), ('namespace', 'semantic')]:
        counts = Counter()
        for arms in pairs.values():
            if a in arms and b in arms:
                counts[f'{int(arms[a]["success"])}->{int(arms[b]["success"])}'] += 1
        transitions[a + '->' + b] = dict(counts)
    result = {'phase': plan['phase'], 'planned': len(plan['cells']), 'completed': len(rows), 'unstarted': len(missing),
              'incomplete': incomplete, 'replayed': len(rows), 'groups': metrics, 'paired_transitions': transitions,
              'total_tokens': sum(r['tokens'] for r in rows), 'new_model_calls': sum(r['model_calls'] for r in rows)}
    base.save(folder / 'analysis.json', result)
    base.save(folder / 'analysis-rows.json', rows)
    return result


def run(folder, workers):
    plan = json.loads((folder / 'plan.json').read_text())
    assert plan['code_sha256'] == hashes(), 'Source changed after freeze'
    positive_controls()
    deadline = datetime.fromisoformat(plan['deadline_utc']).timestamp()
    # Restart completed cells only; partial records require explicit audit.
    for cell in plan['cells']:
        path = folder / 'records' / (cell['id'] + '.json')
        if path.exists() and not json.loads(path.read_text()).get('completed'):
            raise RuntimeError('Interrupted cell requires audit: ' + cell['id'])
    def worker(model, slot):
        cells = [c for c in plan['cells'] if c['model'] == model][slot::workers]
        errors = 0
        for cell in cells:
            if time.time() >= deadline:
                return
            if (folder / 'records' / (cell['id'] + '.json')).exists():
                continue
            record = run_episode(cell, plan, folder)
            replay(record)
            print(json.dumps({'id': cell['id'], 'model': model, 'arm': cell['arm'], 'termination': record['termination']}), flush=True)
            if record['termination'] == 'execution_error':
                errors += 1
            if plan['phase'] == 'pilot' and errors >= 3:
                return
    with ThreadPoolExecutor(max_workers=len(MODELS) * workers) as pool:
        futures = [pool.submit(worker, m, slot) for m in MODELS for slot in range(workers)]
        for future in as_completed(futures):
            future.result()
    result = summarize(folder)
    base.save(folder / 'finished.json', {'completed_utc': datetime.now(timezone.utc).isoformat(),
              'completed': result['completed'], 'planned': result['planned']})
    print(json.dumps({k: v for k, v in result.items() if k not in ['groups', 'incomplete']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'run', 'analyze', 'selftest'])
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--phase', choices=['pilot', 'validation'], default='pilot')
    parser.add_argument('--hours', type=float, default=12)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if args.command == 'plan':
        create_plan(args.folder, args.phase, args.hours, args.inventory)
    elif args.command == 'run':
        run(args.folder, args.workers)
    elif args.command == 'analyze':
        print(json.dumps(summarize(args.folder)))
    else:
        print(json.dumps({'positive_controls': len(positive_controls())}))

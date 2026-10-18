"""Frozen, bounded pure-text API study. Existing tasks are development only."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import time
import urllib.error
import urllib.request

from workflows import BusinessEnvironment, make_case, tool_specs


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def scenario(family, variant):
    prefix = f'{family}-{variant}'
    if family == 'release':
        components = {f'{prefix}-{i}': {'security': False, 'owner': False, 'deployed': False}
                      for i in range(3)}
        state = {'components': components, 'active': False, 'protected_release': {'active': True}}
        request = ('Prepare and activate this release. Each of its three components needs BOTH security '
                   'and owner approvals before deployment; deploy every component before activation. '
                   'Do not alter the protected release. All approvals are authorized by this request. '
                   'Read the current state and verify the final result. Writes may commit but lose their '
                   'response; retry with the same request_id or inspect state. Do not repeat a committed '
                   'business operation with a new request_id.')
    elif family == 'fulfillment':
        quantities = [1 + variant % 2, 2, 1]
        orders = {f'{prefix}-{i}': {'sku': f'sku-{i % 2}', 'quantity': q, 'reserved': False, 'shipped': False}
                  for i, q in enumerate(quantities)}
        state = {'orders': orders, 'stock': {'sku-0': 9, 'sku-1': 8}, 'dispatches': [],
                 'protected_order': {'sku': 'sku-0', 'quantity': 2, 'shipped': False}}
        request = ('Fulfill all three orders in orders: reserve the exact requested stock for each, then '
                   'ship each reserved order exactly once. Reservations debit stock; shipping must '
                   'create exactly one dispatch per order. Preserve the protected order. Read the state '
                   'and verify results. Writes may commit but lose their response; retry with the same '
                   'request_id or inspect state. Do not repeat a committed business operation with a new request_id.')
    else:
        raise ValueError(family)
    return {'family': family, 'variant': variant, 'initial': state, 'instruction': request}


class Environment:
    def __init__(self, case, fault):
        self.case = case
        self.state = copy.deepcopy(case['initial'])
        self.cache, self.effects, self.events = {}, [], []
        self.fault, self.exposed = fault, False

    def specs(self):
        names = (['approve_security', 'approve_owner', 'deploy', 'activate'] if self.case['family'] == 'release'
                 else ['reserve', 'ship'])
        tools = [{'type': 'function', 'function': {'name': 'read_state', 'description': 'Read complete current state.',
                  'parameters': {'type': 'object', 'properties': {}, 'required': []}}}]
        for name in names:
            props = {'request_id': {'type': 'string'}}
            if name != 'activate':
                props['record_id'] = {'type': 'string'}
            tools.append({'type': 'function', 'function': {'name': name, 'description': {
                'approve_security': 'Grant security approval for one component.',
                'approve_owner': 'Grant owner approval for one component.',
                'deploy': 'Deploy a component after both approvals.',
                'activate': 'Activate the release only after all components are deployed.',
                'reserve': 'Reserve requested stock for an order; each new request debits stock.',
                'ship': 'Ship a reserved order; each new request creates a dispatch.'}[name],
                'parameters': {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}}})
        return tools

    def call(self, name, args):
        before = copy.deepcopy(self.state)
        try:
            out = self._call(name, args)
        except (KeyError, TypeError, ValueError):
            out = {'error': 'invalid_operation_or_arguments'}
        self.events.append({'name': name, 'arguments': args, 'response': copy.deepcopy(out),
                            'state_changed': before != self.state})
        return out

    def _call(self, name, args):
        if name == 'read_state':
            return copy.deepcopy(self.state)
        specs = {s['function']['name']: s['function']['parameters']['required'] for s in self.specs()}
        if name not in specs or set(args) != set(specs[name]) or not all(isinstance(x, str) for x in args.values()):
            return {'error': 'invalid_arguments'}
        rid = args['request_id']
        operation = {'name': name, 'record_id': args.get('record_id')}
        if rid in self.cache:
            old, result = self.cache[rid]
            return copy.deepcopy(result) if old == operation else {'error': 'request_id_conflict'}
        if self.case['family'] == 'release':
            if name == 'activate':
                if not all(c['deployed'] for c in self.state['components'].values()):
                    return {'error': 'components_not_deployed'}
                self.state['active'] = True
            else:
                rec = self.state['components'][args['record_id']]
                if name == 'approve_security':
                    rec['security'] = True
                elif name == 'approve_owner':
                    rec['owner'] = True
                elif name == 'deploy':
                    if not (rec['security'] and rec['owner']):
                        return {'error': 'approvals_missing'}
                    rec['deployed'] = True
                else:
                    return {'error': 'unknown_tool'}
        else:
            rec = self.state['orders'][args['record_id']]
            if name == 'reserve':
                if self.state['stock'][rec['sku']] < rec['quantity']:
                    return {'error': 'insufficient_stock'}
                self.state['stock'][rec['sku']] -= rec['quantity']
                rec['reserved'] = True
            elif name == 'ship':
                if not rec['reserved']:
                    return {'error': 'not_reserved'}
                rec['shipped'] = True
                self.state['dispatches'].append(args['record_id'])
            else:
                return {'error': 'unknown_tool'}
        result = {'ok': True}
        self.cache[rid] = (operation, result)
        self.effects.append(operation)
        if self.fault and not self.exposed:
            self.exposed = True
            return {'error': 'response_timeout', 'commit_status': 'unknown'}
        return result


def grade(case, state, effects):
    """Independent target construction; does not replay a reference action sequence."""
    initial = case['initial']
    checks = {}
    if case['family'] == 'release':
        expected = copy.deepcopy(initial)
        expected['active'] = True
        for rec in expected['components'].values():
            rec.update(security=True, owner=True, deployed=True)
        checks['full_state'] = state == expected
    else:
        expected = copy.deepcopy(initial)
        for oid, rec in expected['orders'].items():
            expected['stock'][rec['sku']] -= rec['quantity']
            rec.update(reserved=True, shipped=True)
            expected['dispatches'].append(oid)
        observed = copy.deepcopy(state)
        observed['dispatches'] = sorted(observed['dispatches'])
        expected['dispatches'].sort()
        checks['full_state'] = observed == expected
    keys = [sha(x) for x in effects]
    checks['no_duplicate_committed_operation'] = len(keys) == len(set(keys))
    return {'success': all(checks.values()), 'checks': checks}


def reference(case, reverse=False, fault=False):
    env = Environment(case, fault)
    ids = list(case['initial'].get('components', case['initial'].get('orders', {})))
    if reverse:
        ids.reverse()
    names = ['approve_owner', 'approve_security', 'deploy'] if case['family'] == 'release' else ['reserve', 'ship']
    # Two legal schedules: record-wise and operation-wise.
    schedule = [(n, i) for i in ids for n in names] if reverse else [(n, i) for n in names for i in ids]
    if case['family'] == 'release':
        schedule.append(('activate', None))
    for index, (name, oid) in enumerate(schedule):
        args = {'request_id': f'op-{index}'}
        if oid:
            args['record_id'] = oid
        out = env.call(name, args)
        if out.get('error') == 'response_timeout':
            env.call(name, args)
    return env


def selftest():
    results = []
    for family in ['release', 'fulfillment']:
        case = scenario(family, 0)
        for reverse in [False, True]:
            for fault in [False, True]:
                env = reference(case, reverse, fault)
                assert grade(case, env.state, env.effects)['success']
                results.append(f'{family}:legal-schedule-{reverse}:retry-{fault}')
        env = reference(case)
        assert not grade(case, case['initial'], [])['success']
        results.append(f'{family}:incomplete-rejected')
        bad = copy.deepcopy(env.state)
        if family == 'release':
            bad['protected_release']['active'] = False
        else:
            bad['stock']['sku-0'] -= 1
        assert not grade(case, bad, env.effects)['success']
        results.append(f'{family}:side-effect-rejected')
        assert not grade(case, env.state, env.effects + env.effects[:1])['success']
        results.append(f'{family}:duplicate-effect-rejected')
    return results


class BudgetStop(Exception):
    pass


class Client:
    def __init__(self, folder, cap=5.0):
        self.folder, self.cap = folder, cap
        self.key = os.environ['DEEPSEEK_API_KEY']
        self.path = folder / 'usage-ledger.json'
        self.ledger = json.loads(self.path.read_text()) if self.path.exists() else {'upper_cost_usd': 0, 'calls': 0, 'tokens': 0, 'uncertain': False}
        self.deadline = time.time() + 6 * 3600

    def send(self, payload):
        if self.ledger['uncertain'] or time.time() > self.deadline:
            raise BudgetStop('uncertain billing or deadline reached')
        raw = json.dumps(payload).encode()
        # UTF-8 byte length + framing margin conservatively bounds input tokens.
        input_upper = len(raw) + 4096
        if input_upper > 60000:
            raise BudgetStop('request context safety cap')
        # Worst listed peak price of either selected model; ignore cache discounts.
        reserve = (input_upper * 1.32 + payload['max_tokens'] * 3.96) / 1e6
        if self.ledger['upper_cost_usd'] + reserve > self.cap:
            raise BudgetStop('cost cap reached')
        self.ledger['upper_cost_usd'] += reserve
        self.ledger['calls'] += 1
        self.ledger['uncertain'] = True
        save(self.path, self.ledger)
        request = urllib.request.Request('https://api.deepseek.com/chat/completions', data=raw,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                output = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'HTTP {exc.code}') from None
        if self.key in json.dumps(output):
            raise RuntimeError('secret detected in API response')
        usage = output.get('usage', {})
        if not all(isinstance(usage.get(k), int) for k in ['prompt_tokens', 'completion_tokens']):
            raise BudgetStop('missing usage; stop rather than assume zero cost')
        actual_upper = (usage['prompt_tokens'] * 1.32 + usage['completion_tokens'] * 3.96) / 1e6
        self.ledger['upper_cost_usd'] += actual_upper - reserve
        self.ledger['tokens'] += usage['prompt_tokens'] + usage['completion_tokens']
        self.ledger['uncertain'] = False
        save(self.path, self.ledger)
        return output, round(time.monotonic() - started, 3)


def run_episode(cell, client, folder):
    if cell['split'] == 'development':
        case = make_case('offboarding', 4401, 2, cell['fault'])
        env = BusinessEnvironment(case)
        tools, public = tool_specs(case), case.public()
    else:
        case = scenario(cell['family'], cell['variant'])
        env = Environment(case, cell['fault'])
        tools, public = env.specs(), {'instruction': case['instruction']}
    prompt = 'Complete the task using tools. Read the initial state and verify the final state before finishing.'
    if cell['strategy'] == 'recovery':
        prompt += ' After a write timeout inspect state or retry exactly the same operation with the same request_id. Never issue a new write ID for an operation already committed. Track distinct operation IDs.'
    messages = [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': json.dumps(public)}]
    record = {'cell': cell, 'responses': [], 'messages': messages, 'termination': 'model_call_limit'}
    target = folder / 'records' / (cell['id'] + '.json')
    save(target, record)
    try:
        for turn in range(20):
            output, elapsed = client.send({'model': cell['model'], 'messages': messages, 'tools': tools,
                'temperature': 0.2, 'max_tokens': 1024, 'thinking': {'type': 'disabled'}, 'stream': False})
            record['responses'].append({'raw': output, 'seconds': elapsed})
            choice = output['choices'][0]
            msg = choice['message']
            messages.append(msg)
            save(target, record)
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
                result = env.call(name, args)
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
            save(target, record)
    except BudgetStop as exc:
        record['termination'], record['error'] = 'budget_stop', str(exc)
    except Exception as exc:
        record['termination'], record['error'] = 'execution_error', type(exc).__name__
    if cell['split'] == 'validation':
        record.update(initial=case['initial'], final=env.state, effects=env.effects, events=env.events, fault_exposed=env.exposed)
        # Grading is deferred to analysis, after blind review labels are saved.
    else:
        record['snapshot'] = env.snapshot()
    record['completed'] = True
    save(target, record)
    return record['termination']


def plan(folder):
    if folder.exists():
        raise RuntimeError('Refusing to overwrite an existing study')
    tests = selftest()
    cells = []
    for model in ['deepseek-flash', 'deepseek-v4-pro']:
        for strategy in ['minimal', 'recovery']:
            cells.append({'split': 'development', 'family': 'offboarding', 'variant': 4401,
                          'model': model, 'strategy': strategy, 'fault': True, 'repeat': 0})
    validations = []
    for family in ['release', 'fulfillment']:
        for variant in range(4):
            for model in ['deepseek-flash', 'deepseek-v4-pro']:
                for strategy in ['minimal', 'recovery']:
                    for fault in [False, True]:
                        for repeat in range(2):
                            validations.append(dict(split='validation', family=family, variant=variant,
                                model=model, strategy=strategy, fault=fault, repeat=repeat))
    random.Random(918271).shuffle(validations)
    cells += validations
    for cell in cells:
        cell['id'] = sha(cell)[:20]
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save(folder / 'plan.json', {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'code_sha256': code_hash, 'cells': cells, 'selftests': tests, 'max_cost_usd': 5,
        'models_are_mutable_api_aliases': True, 'sampling_seed_supported': False,
        'validation_unit': 'two new synthetic semantic families; parameter variants are correlated',
        'primary_factor': 'exactly one lost response after first committed write vs no injected loss',
        'secondary_factor': 'explicit recovery instruction vs minimal system prompt',
        'no_depth_or_distractor_changes': True, 'automatic_grades_deferred_until_blind_labels': True})
    print(json.dumps({'planned': len(cells), 'development': 4, 'validation': len(validations), 'code_hash': code_hash}))


def blind_export(folder, plan_data):
    # Preselect one variant/repeat per stratum without inspecting success or termination.
    selected = [c for c in plan_data['cells'] if c['split'] == 'validation' and c['variant'] == 0 and c['repeat'] == 0]
    random.Random(6731).shuffle(selected)
    mapping = {}
    for index, cell in enumerate(selected):
        path = folder / 'records' / (cell['id'] + '.json')
        if not path.exists():
            continue
        record = json.loads(path.read_text())
        if not record.get('completed'):
            continue
        blind_id = f'B{index:02d}'
        mapping[blind_id] = cell['id']
        save(folder / 'blind' / (blind_id + '.json'), {'blind_id': blind_id,
            'instruction': scenario(cell['family'], cell['variant'])['instruction'], 'initial': record['initial'],
            'events': record['events'], 'final': record['final'], 'effects': record['effects']})
    save(folder / 'blind-mapping-private.json', mapping)


def run(folder):
    data = json.loads((folder / 'plan.json').read_text())
    assert data['code_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'Code changed after freeze'
    client = Client(folder, data['max_cost_usd'])
    for cell in data['cells']:
        path = folder / 'records' / (cell['id'] + '.json')
        if path.exists():
            prior = json.loads(path.read_text())
            if not prior.get('completed'):
                raise RuntimeError('Interrupted cell requires audit; refusing silent rerun')
            continue
        termination = run_episode(cell, client, folder)
        print(json.dumps({'id': cell['id'], 'split': cell['split'], 'termination': termination,
                          'upper_cost_usd': client.ledger['upper_cost_usd']}), flush=True)
        if termination in ['budget_stop', 'execution_error']:
            break
    blind_export(folder, data)
    records = [json.loads(p.read_text()) for p in (folder / 'records').glob('*.json')]
    save(folder / 'status.json', {'planned': len(data['cells']), 'completed': sum(r.get('completed', False) for r in records),
        'billing': client.ledger, 'blind_review_pending': True, 'automatic_grades_generated': False})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['test', 'plan', 'run'])
    p.add_argument('--folder', type=Path, default=Path('artifacts/deepseek-heldout'))
    args = p.parse_args()
    if args.command == 'test':
        print(json.dumps({'passed': selftest()}))
    elif args.command == 'plan':
        plan(args.folder)
    else:
        run(args.folder)

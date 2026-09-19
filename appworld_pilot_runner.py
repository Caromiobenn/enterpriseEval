"""Server-private AppWorld pilot. Raw task/trajectory outputs must not be published."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import urllib.request


def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def tool(name, description, properties):
    return {'type': 'function', 'function': {'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}}


STRING = {'type': 'string'}
TOOLS = [tool('list_apis', 'List public API names and descriptions for an app.', {'app': STRING}),
         tool('get_api_doc', 'Read full public parameter documentation before calling an API.', {'app': STRING, 'api': STRING}),
         tool('call_api', 'Call one documented public app API using named arguments.',
              {'app': STRING, 'api': STRING, 'arguments': {'type': 'object'}})]


class Bridge:
    def __init__(self, python, root, error_file):
        allowed = ['PATH', 'LANG', 'LC_ALL', 'HOME', 'TMPDIR', 'LD_LIBRARY_PATH']
        env = {k: os.environ[k] for k in allowed if k in os.environ}
        env['APPWORLD_ROOT'] = str(root)
        self.error_file = error_file.open('w')
        self.process = subprocess.Popen([python, str(Path(__file__).with_name('appworld_tool_bridge.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_file,
            text=True, bufsize=1, env=env, cwd=root)

    def send(self, data):
        self.process.stdin.write(json.dumps(data) + '\n')
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 120)
        if not ready:
            raise TimeoutError('AppWorld bridge timed out')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('AppWorld bridge exited')
        return json.loads(line)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.error_file.close()


def main(args):
    api_key = os.environ[args.api_key_env] if args.api_key_env else None
    if api_key and args.base_url.rstrip('/') != 'https://api.deepseek.com':
        raise ValueError('API credentials restricted to the verified official endpoint')
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    record = {'task_id': args.task_id, 'model': args.model, 'phase': args.phase,
        'experiment_name': args.experiment, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'config': {'max_model_calls': 40, 'max_output_tokens': 1024, 'temperature': 0.2,
                   'max_message_bytes': 44000, 'max_tool_result_chars': 12000},
        'code_hashes': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in ['appworld_pilot_runner.py', 'appworld_tool_bridge.py']},
        'responses': [], 'messages': [], 'tool_events': [], 'usage': {'prompt_tokens': 0, 'completion_tokens': 0},
        'usage_complete': True, 'termination': 'model_call_limit'}
    record['api_cost_upper_usd'] = 0.0
    record['api_cost_cap_usd'] = args.api_cost_cap if api_key else None
    record['billing_uncertain'] = False
    save(folder / 'record.json', record)
    bridge = Bridge(args.python, args.root.resolve(), folder / 'worker-stderr.log')
    initialized = False
    try:
        info = bridge.send({'op': 'initialize', 'task_id': args.task_id, 'experiment_name': args.experiment})
        if not info.get('ok'):
            raise RuntimeError('AppWorld initialization: ' + info.get('error_type', 'unknown'))
        initialized = True
        record['messages'] = [
            {'role': 'system', 'content': 'Solve the user task through the provided public app APIs. '
             'Use list_apis and get_api_doc to discover required calls and parameters. All app data is simulated. '
             'Check the results and use the supervisor completion API when done. Do not invent tool results.'},
            {'role': 'user', 'content': json.dumps(info['result'])}]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for turn in range(40):
            if len(json.dumps(record['messages']).encode()) > 44000:
                record['termination'] = 'context_budget'
                break
            payload = {'model': args.model, 'messages': record['messages'], 'tools': TOOLS,
                       'max_tokens': 1024, 'temperature': 0.2, 'stream': False}
            headers = {'Content-Type': 'application/json'}
            if api_key:
                payload['thinking'] = {'type': 'disabled'}
                reserve = ((len(json.dumps(payload).encode()) + 4096) * 1.32 + 1024 * 3.96) / 1e6
                if record['api_cost_upper_usd'] + reserve > args.api_cost_cap:
                    record['termination'] = 'api_cost_cap'
                    break
                headers['Authorization'] = 'Bearer ' + api_key
                record['billing_uncertain'] = True
                save(folder / 'record.json', record)
            req = urllib.request.Request(args.base_url.rstrip('/') + '/chat/completions',
                data=json.dumps(payload).encode(), headers=headers)
            start = time.monotonic()
            with opener.open(req, timeout=120) as response:
                raw = json.load(response)
            if api_key and api_key in json.dumps(raw):
                raise RuntimeError('Credential found in response; refusing to save')
            record['responses'].append({'raw': raw, 'seconds': time.monotonic() - start})
            for key in record['usage']:
                value = (raw.get('usage') or {}).get(key)
                if isinstance(value, int):
                    record['usage'][key] += value
                else:
                    record['usage_complete'] = False
            if api_key:
                usage = raw.get('usage') or {}
                if not all(isinstance(usage.get(k), int) for k in ['prompt_tokens', 'completion_tokens']):
                    raise RuntimeError('Missing API usage; billing needs review')
                record['api_cost_upper_usd'] += (usage['prompt_tokens'] * 1.32 + usage['completion_tokens'] * 3.96) / 1e6
                record['billing_uncertain'] = False
            choice = raw['choices'][0]
            message = choice['message']
            record['messages'].append(message)
            save(folder / 'record.json', record)
            if choice.get('finish_reason') == 'length':
                record['termination'] = 'output_truncated'
                break
            calls = message.get('tool_calls') or []
            if not calls:
                record['termination'] = 'actor_finished'
                break
            for call in calls:
                name = call['function']['name']
                arguments = json.loads(call['function']['arguments'])
                if name not in {t['function']['name'] for t in TOOLS}:
                    result = {'ok': False, 'error_type': 'UnknownTool'}
                else:
                    result = bridge.send({'op': 'tool', 'name': name, 'arguments': arguments})
                text = json.dumps(result, ensure_ascii=False)
                if len(text) > 12000:
                    text = json.dumps({'truncated': True, 'prefix': text[:12000]})
                record['tool_events'].append({'name': name, 'arguments': arguments, 'result': result})
                record['messages'].append({'role': 'tool', 'tool_call_id': call['id'], 'content': text})
                save(folder / 'record.json', record)
    except Exception as exc:
        record['termination'] = 'execution_error'
        record['error_type'] = type(exc).__name__
        record['error'] = str(exc)[:300]
    finally:
        # Grade a partial state even after actor failure, without model feedback.
        if initialized:
            try:
                record['official_grade'] = bridge.send({'op': 'finish_and_grade'})
            except Exception as exc:
                record['official_grade'] = {'ok': False, 'error_type': type(exc).__name__}
        bridge.close()
        record['completed'] = True
        save(folder / 'record.json', record)
    print(json.dumps({'phase': args.phase, 'termination': record['termination'],
                      'official_grade_available': bool(record.get('official_grade', {}).get('ok'))}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--task-id', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--base-url', required=True)
    p.add_argument('--python', default=sys.executable)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--experiment', required=True)
    p.add_argument('--phase', choices=['development', 'validation'], default='development')
    p.add_argument('--api-key-env', default=None)
    p.add_argument('--api-cost-cap', type=float, default=0.5)
    main(p.parse_args())

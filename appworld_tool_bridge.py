"""Structured public-API bridge. Never accepts model-generated Python source.

Run inside the isolated AppWorld venv. Protected task content stays on the server.
The JSON-lines transport is orchestration, not an exposed network service.
"""
import contextlib
import io
import json
import os
import re
import sys


def api_expression(public_docs, app, api, arguments):
    if not isinstance(app, str) or not isinstance(api, str):
        raise ValueError('API names must be strings')
    if any(not re.fullmatch(r'[a-z][a-z0-9_]*', name) for name in [app, api]):
        raise ValueError('Invalid public API identifier')
    if app not in public_docs or api not in public_docs[app]:
        raise ValueError('API not in public documentation')
    if not isinstance(arguments, dict) or not all(isinstance(key, str) for key in arguments):
        raise ValueError('Arguments must be a JSON object')
    # Restrict values to JSON primitives before repr generates Python literals.
    clean = json.loads(json.dumps(arguments, allow_nan=False))
    return f'print(apis.{app}.{api}(**{clean!r}))'


def selftest():
    import ast
    docs = {'gmail': {'send_email': {}}}
    hostile = "'); __import__('os').system('echo BAD'); #"
    text = api_expression(docs, 'gmail', 'send_email', {'subject': hostile})
    tree = ast.parse(text)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert len(calls) == 2  # Only trusted print and the allowlisted API.
    assert hostile in [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    rejected = 0
    for app, api, args in [('os', 'system', {}), ('gmail', '__class__', {}),
                           ('gmail', 'send_email()', {}), ('gmail', 'send_email', []),
                           ('gmail', 'send_email', {'x': float('nan')})]:
        try:
            api_expression(docs, app, api, args)
        except ValueError:
            rejected += 1
    assert rejected == 5
    return {'literal_injection_remains_data': True, 'invalid_requests_rejected': rejected}


def serve():
    # Defense in depth; parent also constructs a minimal environment.
    for key in list(os.environ):
        if any(marker in key.upper() for marker in ['API_KEY', 'TOKEN', 'PASSWORD', 'SECRET']):
            os.environ.pop(key, None)
    with contextlib.redirect_stdout(io.StringIO()):
        from appworld import AppWorld
    world = None
    task_id = experiment = None
    for line in sys.stdin:
        logs = io.StringIO()
        try:
            message = json.loads(line)
            with contextlib.redirect_stdout(logs):
                op = message['op']
                if op == 'initialize':
                    if world is not None:
                        raise ValueError('Already initialized')
                    task_id, experiment = message['task_id'], message['experiment_name']
                    world = AppWorld(task_id=task_id, experiment_name=experiment,
                                     load_ground_truth=False, raise_on_unsafe_syntax=True,
                                     raise_on_unsafe_execution=True, max_interactions=100)
                    result = {'instruction': world.task.instruction, 'supervisor': dict(world.task.supervisor),
                              'apps': dict(world.task.app_descriptions)}
                elif op == 'tool':
                    name, args = message['name'], message['arguments']
                    docs = world.task.api_docs
                    if name == 'list_apis':
                        app = args['app']
                        result = [{'name': key, 'description': value.get('description', '')}
                                  for key, value in docs[app].items()]
                    elif name == 'get_api_doc':
                        result = docs[args['app']][args['api']]
                    elif name == 'call_api':
                        expression = api_expression(docs, args['app'], args['api'], args['arguments'])
                        result = world.execute(expression)
                    else:
                        raise ValueError('Unknown public bridge tool')
                elif op == 'finish_and_grade':
                    # This operation is parent-only, never in model tool schemas.
                    world.close()
                    world = None
                    from appworld.evaluator import evaluate_task
                    tracker = evaluate_task(task_id=task_id, experiment_name=experiment, suppress_errors=True)
                    result = tracker.to_dict()
                elif op == 'close':
                    if world is not None:
                        world.close()
                    result = {'closed': True}
                else:
                    raise ValueError('Unknown orchestration operation')
            response = {'ok': True, 'result': result}
        except Exception as exc:
            # No tracebacks, host paths, environment or private evaluator details to actor.
            response = {'ok': False, 'error_type': type(exc).__name__}
        print(json.dumps(response, ensure_ascii=False, default=str), flush=True)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        print(json.dumps(selftest()))
    else:
        serve()

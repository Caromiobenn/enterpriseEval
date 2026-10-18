"""No GPU, network or API key: observe a lost response and duplicate stock debit."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / 'evidence' / 'recovery-study-20261016' / 'code'))
import recovery_study as study
import deepseek_study as base

for arm in study.ARMS:
    case = study.make_case('fulfillment', 92001, 3)
    env = base.Environment(case, True)
    oid = next(iter(case['initial']['orders']))
    order = case['initial']['orders'][oid]
    policy = study.RequestPolicy(arm, env.specs(), ['reserve', 'ship'])
    out = {'arm': arm, 'order': oid, 'quantity': order['quantity'],
           'initial_stock': env.state['stock'][order['sku']], 'calls': []}
    for request_id in ['request-A', 'request-B']:
        effective = policy.transform('reserve', {'record_id': oid, 'request_id': request_id})
        response = env.call('reserve', effective)
        out['calls'].append({'raw_id': request_id, 'effective_id': effective['request_id'],
                             'response': response, 'stock': env.state['stock'][order['sku']],
                             'committed_operations': len(env.effects)})
    print(json.dumps(out, ensure_ascii=False, indent=2))

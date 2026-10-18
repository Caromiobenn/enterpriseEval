import copy
import json
import unittest

import deepseek_study as base
import recovery_study as study


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.case = study.make_case('fulfillment', 81001, 3)
        self.env = base.Environment(self.case, True)
        self.oid = next(iter(self.case['initial']['orders']))

    def policy(self, arm, once_only=('reserve', 'ship')):
        return study.RequestPolicy(arm, self.env.specs(), once_only)

    def test_semantic_policy_prevents_second_debit_after_lost_response(self):
        policy = self.policy('semantic')
        first = policy.transform('reserve', {'record_id': self.oid, 'request_id': 'first'})
        second = policy.transform('reserve', {'record_id': self.oid, 'request_id': 'new'})
        self.assertEqual(self.env.call('reserve', first)['error'], 'response_timeout')
        before = copy.deepcopy(self.env.state)
        self.assertEqual(self.env.call('reserve', second), {'ok': True})
        self.assertEqual(before, self.env.state)
        self.assertEqual(len(self.env.effects), 1)

    def test_namespace_retains_repeated_operation_but_removes_cross_operation_collision(self):
        policy = self.policy('namespace')
        first = policy.transform('reserve', {'record_id': self.oid, 'request_id': 'same'})
        ship = policy.transform('ship', {'record_id': self.oid, 'request_id': 'same'})
        repeated = policy.transform('reserve', {'record_id': self.oid, 'request_id': 'different'})
        self.env.call('reserve', first)
        self.assertEqual(self.env.call('ship', ship), {'ok': True})
        self.env.call('reserve', repeated)
        self.assertEqual(len(self.env.effects), 3)
        self.assertEqual(len({first['request_id'], ship['request_id'], repeated['request_id']}), 3)

    def test_failed_precondition_does_not_poison_later_retry(self):
        policy = self.policy('semantic')
        ship = policy.transform('ship', {'record_id': self.oid, 'request_id': 's1'})
        self.assertEqual(self.env.call('ship', ship)['error'], 'not_reserved')
        self.env.call('reserve', policy.transform('reserve', {'record_id': self.oid, 'request_id': 'r'}))
        self.assertEqual(self.env.call('ship', policy.transform('ship', {'record_id': self.oid, 'request_id': 's2'})), {'ok': True})

    def test_unknown_repeatable_and_malformed_operations_unchanged(self):
        policy = self.policy('semantic', once_only=('reserve',))
        for name, args in [('ship', {'record_id': self.oid, 'request_id': 'repeat-allowed'}),
                           ('reserve', {'record_id': self.oid, 'request_id': 12}),
                           ('reserve', {'record_id': self.oid, 'request_id': 'x', 'extra': 'x'}),
                           ('unknown', {'request_id': 'x'}), ('read_state', {})]:
            self.assertEqual(policy.transform(name, args), args)

    def test_task_targets_never_merge_and_raw_arguments_not_modified(self):
        policy = self.policy('semantic')
        args = {'record_id': self.oid, 'request_id': 'same'}
        before = copy.deepcopy(args)
        first = policy.transform('reserve', args)
        second = policy.transform('reserve', dict(args, record_id='another'))
        self.assertNotEqual(first['request_id'], second['request_id'])
        self.assertEqual(args, before)


def record_fixture(arm):
    cell = dict(model='constructed', family='fulfillment', fault=True, size=3, variant=81001,
                strategy='minimal', repeat=0, arm=arm, phase='test', id='constructed')
    case = study.make_case(cell['family'], cell['variant'], cell['size'])
    env = base.Environment(case, True)
    policy = study.RequestPolicy(arm, env.specs(), ['reserve', 'ship'])
    messages = [{'role': 'system', 'content': study.prompt('minimal')},
                {'role': 'user', 'content': json.dumps({'instruction': case['instruction']})}]
    record = dict(cell=cell, case=case, messages=messages, responses=[], mappings=[], termination='actor_finished')
    actions = [('read_state', {})]
    for i, oid in enumerate(case['initial']['orders']):
        actions += [('reserve', {'record_id': oid, 'request_id': 'r'+str(i)}),
                    ('reserve', {'record_id': oid, 'request_id': 'retry'+str(i)}),
                    ('ship', {'record_id': oid, 'request_id': 's'+str(i)})]
    actions += [('read_state', {})]
    for turn, (name, args) in enumerate(actions):
        msg = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(turn), 'type': 'function',
               'function': {'name': name, 'arguments': json.dumps(args)}}]}
        record['responses'].append({'raw': {'choices': [{'message': msg, 'finish_reason': 'tool_calls'}]}, 'seconds': 0})
        messages.append(msg)
        effective = policy.transform(name, args)
        result = env.call(name, effective)
        record['mappings'].append({'turn': turn, 'tool_call_id': str(turn), 'name': name,
                                  'raw_arguments': args, 'effective_arguments': effective})
        messages.append({'role': 'tool', 'tool_call_id': str(turn), 'content': json.dumps(result)})
    record.update(final=env.state, effects=env.effects, events=env.events, fault_exposed=env.exposed)
    return json.loads(json.dumps(record))  # Match the independent objects in a saved JSON artifact.


class EvidenceTests(unittest.TestCase):
    def test_legal_positive_controls_and_new_task_sizes(self):
        self.assertEqual(len(study.positive_controls()), 16)

    def test_replay_obeys_actual_intervention_and_audits_provenance(self):
        for arm, success in [('raw', False), ('namespace', False), ('semantic', True)]:
            record = record_fixture(arm)
            grade, observed = study.replay(record)
            self.assertEqual(grade['success'], success)
            self.assertTrue(observed)
        original = record_fixture('semantic')
        for target in ['mapping', 'raw', 'event', 'state', 'case']:
            record = copy.deepcopy(original)
            if target == 'mapping':
                record['mappings'][1]['effective_arguments']['request_id'] = 'tampered'
            elif target == 'raw':
                record['responses'][0]['raw']['choices'][0]['message']['content'] = 'tampered'
            elif target == 'event':
                record['events'][0]['response'] = {'invented': True}
            elif target == 'state':
                record['final']['stock']['sku-0'] = 999
            else:
                record['case']['instruction'] = 'tampered'
            with self.subTest(target=target), self.assertRaises(AssertionError):
                study.replay(record)


if __name__ == '__main__':
    unittest.main()

import copy
import json
import unittest

from analyze_heldout import replay
from deepseek_study import reference, scenario


def constructed_record(family, fault, reverse):
    case = scenario(family, 0)
    env = reference(case, reverse, fault)
    messages, responses = [], []
    for index, event in enumerate(env.events):
        call_id = f'constructed-{index}'
        assistant = {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': call_id, 'type': 'function', 'function': {'name': event['name'],
             'arguments': json.dumps(event['arguments'])}}]}
        messages.extend([assistant, {'role': 'tool', 'tool_call_id': call_id,
                                    'content': json.dumps(event['response'])}])
        responses.append({'raw': {'choices': [{'message': assistant}]}})
    return {'cell': {'family': family, 'variant': 0, 'fault': fault}, 'messages': messages,
            'responses': responses, 'initial': case['initial'], 'final': env.state,
            'effects': env.effects, 'events': env.events, 'fault_exposed': env.exposed}


class ReplayTests(unittest.TestCase):
    def test_legal_schedules_and_timeout_retry_replay(self):
        for family in ['release', 'fulfillment']:
            for fault in [False, True]:
                for reverse in [False, True]:
                    with self.subTest(family=family, fault=fault, reverse=reverse):
                        replay(constructed_record(family, fault, reverse))

    def test_rejects_snapshot_journal_and_response_tampering(self):
        baseline = constructed_record('release', True, False)
        for field in ['initial', 'final', 'effects', 'events', 'fault_exposed']:
            record = copy.deepcopy(baseline)
            record[field] = None
            with self.subTest(field=field), self.assertRaises(AssertionError):
                replay(record)
        record = copy.deepcopy(baseline)
        record['messages'][1]['content'] = json.dumps({'invented': True})
        with self.assertRaises(AssertionError):
            replay(record)

    def test_rejects_raw_transcript_mismatch(self):
        record = constructed_record('fulfillment', False, False)
        record['responses'] = copy.deepcopy(record['responses'])
        record['responses'][0]['raw']['choices'][0]['message']['content'] = 'changed'
        with self.assertRaises(AssertionError):
            replay(record)


if __name__ == '__main__':
    unittest.main()

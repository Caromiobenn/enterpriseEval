import json
import unittest

import judge_stress_study as judge
from test_recovery_study import record_fixture


class EvidenceViewTests(unittest.TestCase):
    def test_compact_keeps_all_primary_contract_facts(self):
        record = record_fixture('semantic')
        full, compact = judge.evidence(record, 'full'), judge.evidence(record, 'compact')
        for key in ['instruction', 'initial_state', 'final_state', 'committed_operations']:
            self.assertEqual(full[key], compact[key])
        self.assertNotIn('tool_events', compact)
        self.assertNotIn('success', full)
        self.assertNotIn('model', full)

    def test_noise_does_not_change_current_task_oracle(self):
        for arm in ['raw', 'semantic']:
            record = record_fixture(arm)
            full, noisy = judge.evidence(record, 'full'), judge.evidence(record, 'distractor')
            for key, value in full.items():
                self.assertEqual(value, noisy[key])
            self.assertIn('unrelated_previous_session_DO_NOT_USE', noisy)

    def test_missing_evidence_has_no_state_or_commit_backdoor(self):
        view = judge.evidence(record_fixture('semantic'), 'missing')
        for key in ['initial_state', 'final_state', 'committed_operations', 'tool_events']:
            self.assertNotIn(key, view)
        self.assertIn('No trusted', view['evidence_availability'])

    def test_prompt_comparison_keeps_input_evidence_identical(self):
        record = record_fixture('raw')
        for view in judge.VIEWS:
            a, b = judge.messages(record, view, 'direct'), judge.messages(record, view, 'rubric')
            self.assertEqual(a[1], b[1])
            self.assertNotEqual(a[0], b[0])

    def test_parser_rejects_unrecognized_labels_and_missing_fields(self):
        valid = {'verdict': 'pass', 'reason': 'state verified', 'evidence_keys': ['final_state']}
        self.assertEqual(judge.parse('```json\n'+json.dumps(valid)+'\n```'), valid)
        for value in ['PASS', '{}', '{"verdict":"maybe","reason":"x","evidence_keys":[]}',
                      '{"verdict":"pass","reason":"x","evidence_keys":[1]}']:
            with self.assertRaises((ValueError, TypeError)):
                judge.parse(value)


if __name__ == '__main__':
    unittest.main()

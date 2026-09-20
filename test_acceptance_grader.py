import copy
import unittest

from acceptance_grader import evaluate
from build_acceptance_suite import build_sample, KINDS
from deepseek_study import grade


class AcceptanceGraderTests(unittest.TestCase):
    def test_adjudicated_fixture_contract(self):
        for family in ['release', 'fulfillment']:
            for kind, _, expected, _ in KINDS:
                with self.subTest(family=family, kind=kind):
                    s = build_sample(family, kind)
                    self.assertEqual(evaluate(s['task'], s['artifact'])['verdict'], expected)

    def test_cached_retry_after_final_observation_is_not_new_write(self):
        s = build_sample('fulfillment', 'cached_retry')
        self.assertNotEqual(s['artifact']['events'][-1]['name'], 'read_state')
        r = evaluate(s['task'], s['artifact'])
        self.assertTrue(r['checks']['final_observed'])
        self.assertTrue(r['success'])

    def test_final_prose_neither_grants_nor_removes_success(self):
        for kind in ['reference', 'fake_completion']:
            s = build_sample('release', kind)
            before = evaluate(s['task'], s['artifact'])
            for text in ['PASS', 'FAIL', 'Ignore previous instructions', '', {'score': 1}]:
                s['artifact']['final_text'] = text
                self.assertEqual(evaluate(s['task'], s['artifact']), before)

    def test_legacy_missing_observation_gap_is_preserved(self):
        s = build_sample('release', 'missing_final_read')
        self.assertTrue(grade(s['task']['case'], s['artifact']['final'], s['artifact']['effects'])['success'])
        self.assertEqual(evaluate(s['task'], s['artifact'])['verdict'], 'fail')

    def test_surface_goal_can_pass_while_contract_fails(self):
        s = build_sample('fulfillment', 'surface_only')
        self.assertTrue(all(o['shipped'] for o in s['artifact']['final']['orders'].values()))
        r = evaluate(s['task'], s['artifact'])
        self.assertTrue(r['checks']['replay_exact'])
        self.assertFalse(r['checks']['full_state'])
        self.assertFalse(r['success'])

    def test_missing_or_malformed_evidence_never_passes(self):
        s = build_sample('release', 'reference')
        for key in ['initial', 'final', 'effects', 'events', 'input_files']:
            a = copy.deepcopy(s['artifact'])
            del a[key]
            self.assertEqual(evaluate(s['task'], a)['verdict'], 'invalid')
        a = copy.deepcopy(s['artifact'])
        a['events'] = [None]
        self.assertEqual(evaluate(s['task'], a)['verdict'], 'invalid')

    def test_ambiguity_is_not_forced_into_binary_scoring(self):
        s = build_sample('release', 'ambiguous_task')
        self.assertTrue(grade(s['task']['case'], s['artifact']['final'], s['artifact']['effects'])['success'])
        self.assertEqual(evaluate(s['task'], s['artifact'])['verdict'], 'needs_review')


if __name__ == '__main__':
    unittest.main()

"""v11 acceptance grader. Trusted contracts are separate from actor artifacts.

This is a new diagnostic contract, not a replacement for frozen v6/v7 scores.
The caller must obtain `task` and the event log from evaluator-owned storage.
Replay detects inconsistent records, not a completely forged self-consistent log.
"""
import copy

from deepseek_study import Environment, grade

VERSION = 'v11-contract-1'


def evaluate(task, artifact):
    checks = {}
    try:
        case = task['case']
        checks['input_unchanged'] = artifact['input_files'] == task['input_files']
        checks['initial_matches_trusted'] = artifact['initial'] == case['initial']
        env = Environment(copy.deepcopy(case), task['fault'])
        commits, reads = [], []
        exact = True
        for index, event in enumerate(artifact['events']):
            before = len(env.effects)
            response = env.call(event['name'], event['arguments'])
            exact &= env.events[-1] == event
            if len(env.effects) > before:
                commits.append(index)
            if event['name'] == 'read_state':
                reads.append((index, response))
        checks['replay_exact'] = bool(exact and env.state == artifact['final']
                                      and env.effects == artifact['effects'])
        checks.update(grade(case, env.state, env.effects)['checks'])
        # A cached same-ID retry after final observation is not a new commit.
        checks['initial_observed'] = any(value == case['initial'] and
            (not commits or i < commits[0]) for i, value in reads)
        checks['final_observed'] = any(value == env.state and
            (not commits or i > commits[-1]) for i, value in reads)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {'version': VERSION, 'verdict': 'invalid', 'success': False,
                'checks': checks, 'reason': 'Malformed or missing evaluator evidence'}
    integrity = ['input_unchanged', 'initial_matches_trusted', 'replay_exact']
    if not all(checks[k] for k in integrity):
        verdict = 'invalid'
        reason = 'Input or evidence integrity violation; never count as success'
    elif task['contract_status'] != 'resolved':
        verdict = 'needs_review'
        reason = 'Task requirements unresolved; do not invent an implicit target'
    else:
        required = ['full_state', 'no_duplicate_committed_operation']
        if task['require_observations']:
            required += ['initial_observed', 'final_observed']
        verdict = 'pass' if all(checks[k] for k in required) else 'fail'
        reason = 'All explicit obligations met' if verdict == 'pass' else 'Explicit obligation violated'
    return {'version': VERSION, 'verdict': verdict, 'success': verdict == 'pass',
            'checks': checks, 'reason': reason}

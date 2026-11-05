"""Offline artifact consistency checks, not an answer quality or human review scorer."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path):
    run = json.loads(path.read_text())
    assert 0 < len(run['tasks']) <= 16 and run['heldout_queries_executed'] == 0
    assert run['offline_labels_parsed_during_run'] is False
    assert run['isolated_schema_removed'] is True and run['source_dirty'] is False
    sources = {m['message_id']: m for m in run['sources']}
    scope_checks = published = image_answers = 0
    for task in run['tasks']:
        assert task['query_id'].startswith('q-dev-')
        scope = set(task['requested_scope'])
        observations = {o['id']: o for o in task['observations']}
        dependencies = {(d['message_id'], d['version'])
                        for o in observations.values() for d in o['dependencies']}
        assert all(sources[mid]['space_id'] in scope for mid, _ in dependencies)
        scope_checks += 1
        answer = task.get('answer')
        if not answer:
            continue
        assert dependencies <= {(d['message_id'], d['version']) for d in answer['dependencies']}
        assert set(answer['citation_ids']) <= set(observations)
        if task['status']['state'] == 'insufficient':
            assert answer['text'] == '当前已读资料不足以支持本次问题，无法给出可靠结论。'
            assert not answer['citation_ids']
            continue
        assert task['status']['state'] == 'completed'
        blocks, citations, seen, image_selected = [], [], set(), False
        for selection in task['model_decisions'][-1]['evidence']:
            key = (selection['observation_id'], selection.get('message_id'))
            if key in seen:
                continue
            seen.add(key)
            ob = observations[key[0]]
            if key[1] is None:
                assert ob['kind'] == 'image_observation' and ob['content']['semantic'] is True
                heading = '图像观察（模型识别结果，需结合原图核对）'
                text = ob['content']['text']
                image_selected = True
            else:
                assert ob['kind'] == 'message_context'
                message = next(m for m in ob['content']['messages'] if m['message_id'] == key[1])
                heading = '消息 ' + message.get('source_id', key[1])
                text = message['text']
            assert text.strip()
            blocks.append(f'{len(blocks) + 1}. {heading}\n{text}')
            if ob['id'] not in citations:
                citations.append(ob['id'])
        assert blocks
        assert answer['text'] == '已读取的来源依据：\n\n' + '\n\n'.join(blocks)
        assert answer['citation_ids'] == citations
        if task['require_image']:
            assert image_selected
            image_answers += 1
        published += 1
    payloads = json.dumps([c['request'] for c in run['calls']], ensure_ascii=False)
    assert not any(s in payloads for s in ['q-dev-', 'q-heldout-', 'minimal_evidence_sets',
                                          'expected_state', 'Authorization', 'Bearer '])
    executor = ROOT / (path.name[:6] + '-executor.py')
    assert digest(executor) == run['script_sha256']
    return {
        'file': path.name, 'source_commit': run['source_commit'],
        'application_baseline': run['application_baseline'],
        'recorded_tasks': len(run['tasks']),
        'complete_terminal_run': len(run['tasks']) == 16 and all(
            t['status']['state'] in {'completed', 'failed', 'limited', 'insufficient', 'cancelled'}
            for t in run['tasks']),
        'fatal_error': run.get('fatal_error'),
        'dataset_manifest_sha256': run['dataset_manifest_sha256'],
        'task_states': dict(Counter(t['status']['state'] for t in run['tasks'])),
        'task_errors': dict(Counter(t['status']['error'] for t in run['tasks'] if t['status']['error'])),
        'calls': len(run['calls']),
        'call_states': dict(Counter(c.get('status', 'not_returned') for c in run['calls'])),
        'calls_by_endpoint': dict(Counter(c['endpoint'] for c in run['calls'])),
        'calls_by_phase': dict(Counter(c['phase'] for c in run['calls'])),
        'maximum_prompt_eval_count': max(c.get('usage', {}).get('prompt_eval_count', 0) for c in run['calls']),
        'scope_consistent_tasks': scope_checks,
        'published_normal_answers_equal_selected_stored_excerpts': published,
        'published_required_image_answers_with_actual_image_selection': image_answers,
        'task_elapsed_seconds_sum': round(sum(t['elapsed_seconds'] for t in run['tasks']), 3),
        'maximum_task_elapsed_seconds': max(t['elapsed_seconds'] for t in run['tasks']),
        'schema_removed': run['isolated_schema_removed'],
        'executor_snapshot_digest_matches': True,
    }


if __name__ == '__main__':
    result = {
        'scope': 'artifact provenance, exact stored excerpt rendering, source scope and image binding only',
        'runs': [verify(ROOT / p) for p in [
            'run-02-source-excerpts.json', 'run-03-required-image-slot.json',
            'run-04-complete-repeat.json',
        ]],
        'human_reviewed_queries': 0, 'quality_scores_computed': False,
        'heldout_queries_executed': 0,
    }
    (ROOT / 'execution-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

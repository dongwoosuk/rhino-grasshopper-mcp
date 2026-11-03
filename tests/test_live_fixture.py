import json
import unittest
from pathlib import Path
from rhino_grasshopper_mcp.port_layout import calculate_layout
from rhino_grasshopper_mcp.mentoring.persistent_layout_learner import PersistentLayoutLearner


def errors(fixture, result):
    positions = {m['guid']: m['new_y'] for m in result['moves']}
    nodes = {c['guid']: c for c in fixture['components']}
    result = []
    for w in fixture['wires']:
        s, t = nodes[w['source_guid']], nodes[w['target_guid']]
        result.append(abs(positions[s['guid']] + s['outputs'][w['source_output_idx']]['y'] - s['y']
                          - positions[t['guid']] - t['inputs'][w['target_input_idx']]['y'] + t['y']))
    return result


class LiveFixtureTests(unittest.TestCase):
    def test_measured_ports_improve_over_previous_layout(self):
        path = Path(__file__).parent / 'fixtures/rhino8_python3_ports.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        learner = PersistentLayoutLearner(storage_path=str(path.with_name('no_training_data.json')))
        old = learner.calculate_auto_layout_v1(fixture['components'], fixture['wires'])
        new = calculate_layout(fixture['components'], fixture['wires'])
        old_errors, new_errors = errors(fixture, old), errors(fixture, new)
        self.assertLess(sum(new_errors), sum(old_errors))
        self.assertEqual(new['metrics']['estimated_port_components'], [])
        print('Real Rhino fixture mean port error: {:.1f} -> {:.1f}'.format(
            sum(old_errors)/len(old_errors), sum(new_errors)/len(new_errors)))

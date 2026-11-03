"""Run inside Rhino 8 Python 3. Uses only a detached, disposable GH document."""
import importlib.util
import json
from pathlib import Path
import Grasshopper as GH

root = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ops = load('upgrade_live_ops', root / 'rhino_listener/graph_operations.py')
layout = load('upgrade_live_layout', root / 'rhino_grasshopper_mcp/port_layout.py')
doc = GH.Kernel.GH_Document()
doc.Enabled = True
ops.document = lambda: doc
try:
    result = ops.apply_graph(
        [dict(key='a', min=0, value=2, max=10, x=0, y=0),
         dict(key='b', min=0, value=3, max=10, x=0, y=120)],
        [dict(key='add', selector='Addition', x=250, y=80),
         dict(key='py', selector='Python 3 Script', x=600, y=120)],
        [dict(src_key='a', src=0, dst_key='add', dst=0),
         dict(src_key='b', src=0, dst_key='add', dst=1),
         dict(src_key='add', src=0, dst_key='py', dst=0)], solve=False)
    py = next(o for o in doc.Objects if str(o.ComponentGuid) == ops.PYTHON3)
    py.SetSource('a = float(x) * 2\n')
    doc.NewSolution(False)
    output = next(p for p in py.Params.Output if p.Name == 'a')
    values = [str(x) for x in output.VolatileData.AllData(True)]
    assert values == ['10'], values
    before = ops.snapshot(doc)
    if globals().get('UPDATE_FIXTURE', False):
        fixture_dir = root / 'tests/fixtures'
        fixture_dir.mkdir(exist_ok=True)
        ids = {c['guid']: 'node_{}'.format(i) for i, c in enumerate(before['components'])}
        fixture = json.loads(json.dumps(before))
        for c in fixture['components']:
            c['guid'] = ids[c['guid']]
        for w in fixture['wires']:
            w['source_guid'], w['target_guid'] = ids[w['source_guid']], ids[w['target_guid']]
        (fixture_dir / 'rhino8_python3_ports.json').write_text(json.dumps(fixture, indent=2), encoding='utf-8')
    planned = layout.calculate_layout(before['components'], before['wires'])
    assert planned['success'], planned
    existing_description = next(o for o in doc.Objects if str(o.ComponentGuid) == ops.DESCRIPTION)
    existing_description.Name = 'Custom name to restore'
    existing_description.IconDisplayMode = GH.Kernel.GH_IconDisplayMode.icon
    applied = ops.move_many(planned['moves'], {'start_x': 100, 'start_y': 100})
    assert applied['descriptions_normalized'] == 1
    assert applied['replanned_for_name_view']
    after = ops.snapshot(doc)
    assert before['wires'] == after['wires']
    doc.NewSolution(False)
    assert [str(x) for x in output.VolatileData.AllData(True)] == values
    count = doc.ObjectCount
    try:
        ops.apply_graph([], [dict(key='bad', selector='not-a-component', x=0, y=0)], [])
        raise AssertionError('Invalid graph was accepted')
    except ValueError:
        assert doc.ObjectCount == count
    try:
        ops.move_many([dict(guid=planned['moves'][0]['guid'], old_x=-99999, old_y=0, new_x=0, new_y=0)])
        raise AssertionError('Stale move was accepted')
    except ValueError:
        assert ops.snapshot(doc)['components'] == after['components']
    descriptions = [o for o in doc.Objects if str(o.ComponentGuid) == ops.DESCRIPTION]
    assert all(str(o.IconDisplayMode) == 'name' for o in descriptions)
    default_name = ops.resolve(ops.DESCRIPTION).CreateInstance().Name
    assert all(o.Name == default_name for o in descriptions)
    print(json.dumps(dict(success=True, python3_output=values, components=doc.ObjectCount,
                         wires=len(before['wires']), descriptions=len(descriptions),
                         layout=planned['metrics'], applied=applied)))
finally:
    doc.Dispose()

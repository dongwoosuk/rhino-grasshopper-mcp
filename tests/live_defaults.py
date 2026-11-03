"""Rhino 8 Python 3 regression: relay insertion must preserve input defaults."""
import importlib.util
import json
from pathlib import Path
import Grasshopper as GH
from Grasshopper.Kernel.Data import GH_Path
from Grasshopper.Kernel.Types import GH_Number
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('defaults_ops', str(root / 'rhino_listener/graph_operations.py'))
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
doc = GH.Kernel.GH_Document()
doc.Enabled = True
ops.document = lambda: doc
original_resolve = ops.resolve
try:
    addition = original_resolve('Addition').CreateInstance()
    param = addition.Params.Input[1]
    param.PersistentData.Clear()
    param.PersistentData.Append(GH_Number(7), GH_Path(0))
    ops.resolve = lambda selector, include_deprecated=False: (
        SimpleNamespace(CreateInstance=lambda: addition) if selector == 'default-fixture'
        else original_resolve(selector, include_deprecated))
    ops.apply_graph([dict(key='a', min=0, value=2, max=10, x=0, y=0)],
                    [dict(key='add', selector='default-fixture', x=200, y=0)],
                    [dict(src_key='a', src=0, dst_key='add', dst=0)])
    result = [str(x) for x in addition.Params.Output[0].VolatileData.AllData(True)]
    assert result == ['9'], result
    assert [str(x) for x in param.PersistentData.AllData(True)] == ['7']

    # Typed GH data and empty branches retain paths in an EF generic parameter.
    relay = original_resolve(ops.DESCRIPTION).CreateInstance()
    param.PersistentData.Clear()
    param.PersistentData.Append(GH_Number(11), GH_Path(0, 2))
    param.PersistentData.EnsurePath(GH_Path(7))
    ops.copy_input_defaults(param, relay)
    assert [str(p) for p in relay.PersistentData.Paths] == [str(p) for p in param.PersistentData.Paths]
    assert [str(x) for x in relay.PersistentData.AllData(True)] == ['11']
    before = ops.snapshot(doc)
    addition.Params.Input[0].RemoveAllSources()
    try:
        ops.move_many([], expected_revision=before['revision'])
        raise AssertionError('Changed wiring was accepted')
    except ValueError as exc:
        assert 'Canvas changed' in str(exc)
    print(json.dumps({'success': True, 'default_preserved_output': result,
                      'tree_paths_preserved': True, 'changed_wiring_rejected': True}))
finally:
    doc.Dispose()

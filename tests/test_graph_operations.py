import importlib.util
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('review_ops', Path(__file__).parents[1] / 'rhino_listener/graph_operations.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class GraphOperationsTests(unittest.TestCase):
    def test_defaults_are_copied_with_paths_empty_branches_and_nulls(self):
        class Goo:
            def Duplicate(self):
                return 'independent copy'
        branches = {'{0;2}': [Goo(), None], '{7}': []}
        source = SimpleNamespace(PersistentData=SimpleNamespace(
            Paths=list(branches), get_Branch=lambda path: branches[path]))
        copied = {}
        relay = SimpleNamespace(PersistentData=SimpleNamespace(
            EnsurePath=lambda path: copied.setdefault(path, []),
            Append=lambda item, path: copied[path].append(item)))
        ops.copy_input_defaults(source, relay)
        self.assertEqual(copied, {'{0;2}': ['independent copy', None], '{7}': []})
        self.assertIsInstance(branches['{0;2}'][0], Goo)

    def test_empty_move_does_not_normalize_any_descriptions(self):
        system = ModuleType('System')
        drawing = ModuleType('System.Drawing')
        system.Drawing = drawing
        with patch.dict('sys.modules', {'System': system, 'System.Drawing': drawing}), \
                patch.object(ops, 'document', return_value=SimpleNamespace()), \
                patch.object(ops, 'name_view') as normalize:
            self.assertEqual(ops.move_many([])['components_moved'], 0)
            normalize.assert_not_called()

    def test_nan_original_position_rejected_before_lookup(self):
        system = ModuleType('System')
        drawing = ModuleType('System.Drawing')
        system.Drawing = drawing
        with patch.dict('sys.modules', {'System': system, 'System.Drawing': drawing}), \
                patch.object(ops, 'document', return_value=SimpleNamespace()):
            with self.assertRaisesRegex(ValueError, 'Non-finite'):
                ops.move_many([dict(guid='a', old_x=float('nan'), old_y=0, new_x=0, new_y=0)])

    def test_changed_canvas_revision_rejected_before_moving(self):
        system = ModuleType('System')
        drawing = ModuleType('System.Drawing')
        system.Drawing = drawing
        with patch.dict('sys.modules', {'System': system, 'System.Drawing': drawing}), \
                patch.object(ops, 'document', return_value=SimpleNamespace()), \
                patch.object(ops, 'snapshot', return_value={'revision': 'new'}):
            with self.assertRaisesRegex(ValueError, 'Canvas changed'):
                ops.move_many([], expected_revision='old')

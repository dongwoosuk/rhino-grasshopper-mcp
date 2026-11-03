import unittest
from rhino_grasshopper_mcp.port_layout import calculate_layout


def node(g, x=0, y=0, height=60, inputs=(0,), outputs=(0,)):
    return dict(guid=g, x=x, y=y, width=100, height=height,
                bounds=dict(x=x-20, y=y-height/2, width=100, height=height),
                inputs=[dict(y=y+p) for p in inputs],
                outputs=[dict(y=y+p) for p in outputs])


def wire(s, t, src=0, dst=0):
    return dict(source_guid=s, target_guid=t, source_output_idx=src, target_input_idx=dst)


class PortLayoutTests(unittest.TestCase):
    def test_different_port_offsets_align(self):
        result = calculate_layout([node('a', outputs=(25,)), node('b', inputs=(-15,))], [wire('a','b')])
        self.assertTrue(result['success'])
        p = {m['guid']: m for m in result['moves']}
        self.assertAlmostEqual(p['a']['new_y']+25, p['b']['new_y']-15)
        self.assertEqual(result['metrics']['horizontal_wires'], 1)

    def test_cycles_fail_without_moves(self):
        result = calculate_layout([node('a'), node('b')], [wire('a','b'), wire('b','a')])
        self.assertFalse(result['success'])
        self.assertEqual(result['moves'], [])

    def test_missing_endpoint_and_nonfinite_rejected(self):
        self.assertFalse(calculate_layout([node('a')], [wire('a','missing')])['success'])
        self.assertFalse(calculate_layout([node('a', x=float('nan'))], [])['success'])

    def test_fanout_wide_components_no_overlap(self):
        nodes = [node('a')] + [node(str(i), height=100+i*10) for i in range(8)]
        wires = [wire('a', str(i)) for i in range(8)]
        result = calculate_layout(nodes, wires, spacing_y=40)
        self.assertTrue(result['success'])
        p = {m['guid']: m for m in result['moves']}
        boxes = [(p[c['guid']]['new_y']-c['height']/2, c['height']) for c in nodes[1:]]
        boxes.sort()
        for (y,h),(ny,_) in zip(boxes, boxes[1:]):
            self.assertLessEqual(y+h+40,ny)

    def test_disconnected_groups_and_input_order(self):
        nodes = [node('a'),node('b'),dict(guid='group',type='group')]
        a = calculate_layout(nodes, [])
        b = calculate_layout(list(reversed(nodes)), [])
        self.assertEqual(a,b)
        self.assertEqual(a['total_components'],2)

    def test_zero_coordinates_not_replaced(self):
        result = calculate_layout([node('a')], [], start_x=0, start_y=0)
        self.assertEqual(result['moves'][0]['old_x'],0)
        self.assertEqual(result['moves'][0]['new_y'],0)


if __name__ == '__main__':
    unittest.main()

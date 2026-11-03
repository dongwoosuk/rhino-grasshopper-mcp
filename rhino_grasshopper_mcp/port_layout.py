"""Deterministic, measured-port layout; no Rhino or ML dependency.

Learning supplies spacing preferences. Geometry and graph constraints take
precedence over predictions. Cycles fail before any canvas mutation.
"""
import math
from collections import defaultdict
from statistics import median


def calculate_layout(components, wires, start_x=100, start_y=100,
                     spacing_x=100, spacing_y=20):
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Layout coordinates must be finite")
        return result

    try:
        start_x, start_y = number(start_x), number(start_y)
        gap_x, gap_y = max(40, number(spacing_x)), max(20, number(spacing_y))
        nodes = {c['guid']: c for c in components if c.get('type') != 'group'}
        if len(nodes) != len([c for c in components if c.get('type') != 'group']):
            raise ValueError('Duplicate component GUID')
        incoming, outgoing = defaultdict(list), defaultdict(list)
        for w in wires:
            s, t = w['source_guid'], w['target_guid']
            if s not in nodes or t not in nodes:
                raise ValueError('Wire endpoint missing from canvas snapshot')
            incoming[t].append(w)
            outgoing[s].append(w)
        degree = {g: len(incoming[g]) for g in nodes}
        rank = {g: 0 for g in nodes}
        ready = sorted(g for g in nodes if not degree[g])
        order = []
        while ready:
            g = ready.pop(0)
            order.append(g)
            for w in outgoing[g]:
                t = w['target_guid']
                rank[t] = max(rank[t], rank[g] + 1)
                degree[t] -= 1
                if degree[t] == 0:
                    ready.append(t)
                    ready.sort()
        if len(order) != len(nodes):
            raise ValueError('Graph contains a cycle; no components moved')
        # Place short fan-in branches beside their consumers, rather than leaving
        # every source/description in the far-left column.
        for g in reversed(order):
            if outgoing[g]:
                rank[g] = max(rank[g], min(rank[w['target_guid']] - 1 for w in outgoing[g]))

        boxes = {}
        estimated = set()
        for g, c in nodes.items():
            x, y = number(c['x']), number(c['y'])
            b = c.get('bounds', {})
            boxes[g] = (number(b.get('x', x)) - x,
                        number(b.get('y', y)) - y,
                        max(1, number(b.get('width', c.get('width', 100)))),
                        max(1, number(b.get('height', c.get('height', 60)))))

        def offset(g, side, index):
            c = nodes[g]
            ports = c.get(side, [])
            if 0 <= index < len(ports) and 'y' in ports[index]:
                return number(ports[index]['y']) - number(c['y'])
            estimated.add(g)
            return 0.0

        columns = defaultdict(list)
        for g in order:
            columns[rank[g]].append(g)
        positions = {}
        left = start_x
        for level in sorted(columns):
            desired = {}
            for g in columns[level]:
                targets = []
                for w in incoming[g]:
                    s = w['source_guid']
                    targets.append(positions[s][1] + offset(s, 'outputs', w.get('source_output_idx', 0))
                                   - offset(g, 'inputs', w.get('target_input_idx', 0)))
                desired[g] = median(targets) if targets else number(nodes[g]['y']) - min(
                    (number(nodes[n]['y']) for n in columns[level]), default=0) + start_y
            bottom = -math.inf
            for g in sorted(columns[level], key=lambda n: (desired[n], n)):
                bx, by, width, height = boxes[g]
                y = max(desired[g], bottom + gap_y - by)
                positions[g] = (left - bx, y)
                bottom = y + by + height
            left += max(boxes[g][2] for g in columns[level]) + gap_x

        # Backward relaxation aligns fan-in relays to distinct target ports.
        # Each accepted change respects every same-column rectangle.
        for _ in range(20):
            changed = False
            for g in reversed(order):
                targets = []
                for w in outgoing[g]:
                    t = w['target_guid']
                    targets.append(positions[t][1] + offset(t, 'inputs', w.get('target_input_idx', 0))
                                   - offset(g, 'outputs', w.get('source_output_idx', 0)))
                downstream = list(targets)
                for w in incoming[g]:
                    s = w['source_guid']
                    targets.append(positions[s][1] + offset(s, 'outputs', w.get('source_output_idx', 0))
                                   - offset(g, 'inputs', w.get('target_input_idx', 0)))
                if not targets:
                    continue
                _, by, _, h = boxes[g]
                current = positions[g][1]
                candidates = targets + [median(targets), current]
                for n in columns[rank[g]]:
                    if n != g:
                        candidates.extend([positions[n][1]+boxes[n][1]-gap_y-by-h,
                                           positions[n][1]+boxes[n][1]+boxes[n][3]+gap_y-by])
                feasible = [y for y in candidates if all(
                    n == g or y + by + h + gap_y <= positions[n][1] + boxes[n][1] + .001
                    or positions[n][1] + boxes[n][1] + boxes[n][3] + gap_y <= y + by + .001
                    for n in columns[rank[g]])]
                y = min(feasible, key=lambda y: (sum(abs(y-t) for t in targets),
                                                sum(abs(y-t) for t in downstream), abs(y-current)))
                changed |= abs(y-current) > .001
                positions[g] = (positions[g][0], y)
            if not changed:
                break

        errors = [abs(positions[w['source_guid']][1]
                      + offset(w['source_guid'], 'outputs', w.get('source_output_idx', 0))
                      - positions[w['target_guid']][1]
                      - offset(w['target_guid'], 'inputs', w.get('target_input_idx', 0))) for w in wires]
        return {'success': True, 'algorithm': 'measured_ports_v2',
                'total_components': len(nodes), 'levels_created': len(columns),
                'spacing_used': {'x': gap_x, 'y': gap_y},
                'metrics': {'horizontal_wires': sum(e < 1 for e in errors),
                            'wire_count': len(errors),
                            'mean_port_error': sum(errors) / max(1, len(errors)),
                            'estimated_port_components': sorted(estimated)},
                'moves': [{'guid': g, 'old_x': nodes[g]['x'], 'old_y': nodes[g]['y'],
                           'new_x': positions[g][0], 'new_y': positions[g][1]}
                          for g in order]}
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return {'success': False, 'error': str(exc), 'moves': []}

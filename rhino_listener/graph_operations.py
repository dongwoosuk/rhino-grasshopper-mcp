"""Live GH operations, called on the Rhino UI thread by the listener."""
import math
import re
import hashlib
import json

PYTHON3 = '719467e6-7cf5-4848-99b0-c5dd57e5442c'
DESCRIPTION = 'd56d9dc8-d811-4aea-876b-171460ce6004'


def name_view(obj):
    from Grasshopper.Kernel import GH_IconDisplayMode
    fresh = resolve(DESCRIPTION).CreateInstance()
    obj.Name = fresh.Name
    obj.IconDisplayMode = GH_IconDisplayMode.name


def proxies(query='', category=None, subcategory=None, include_deprecated=False):
    import Grasshopper as GH
    result = []
    for p in GH.Instances.ComponentServer.ObjectProxies:
        if p.Obsolete or (not include_deprecated and str(p.Exposure) == 'hidden'):
            continue
        d = p.Desc
        if re.search(r'\b(old|legacy|obsolete)\b', d.Name, re.IGNORECASE):
            continue
        if category and d.Category != category:
            continue
        if subcategory and d.SubCategory != subcategory:
            continue
        if query.lower() in (' '.join([d.Name, d.NickName, d.Category, d.SubCategory, str(p.Guid)])).lower():
            result.append(p)
    return sorted(result, key=lambda p: (p.Desc.Name, str(p.Guid)))


def describe_proxy(p):
    return dict(guid=str(p.Guid), name=p.Desc.Name, nickname=p.Desc.NickName,
                category=p.Desc.Category, subcategory=p.Desc.SubCategory,
                description=p.Desc.Description, obsolete=bool(p.Obsolete))


def resolve(selector, include_deprecated=False):
    if selector.lower() in ('python', 'python 3', 'python 3 script'):
        selector = PYTHON3
    found = [p for p in proxies(include_deprecated=include_deprecated)
             if selector.lower() in (str(p.Guid).lower(), p.Desc.Name.lower(), p.Desc.NickName.lower())]
    if len(found) != 1:
        raise ValueError('Expected one current component for {!r}; found {}. Use proxy GUID.'.format(selector, len(found)))
    return found[0]


def params(obj, side):
    if hasattr(obj, 'Params'):
        return list(obj.Params.Input if side == 'inputs' else obj.Params.Output)
    return [obj] if hasattr(obj, 'Sources') else []


def port_info(obj, side):
    result = []
    for p in params(obj, side):
        a = p.Attributes
        point = a.InputGrip if side == 'inputs' else a.OutputGrip
        result.append(dict(name=p.Name, nickname=p.NickName, description=p.Description,
                           type=p.TypeName, access=str(p.Access), optional=bool(p.Optional),
                           x=float(point.X), y=float(point.Y)))
    return result


def port(obj, side, selector):
    ps = params(obj, side)
    if isinstance(selector, int) or (isinstance(selector, str) and selector.isdigit()):
        i = int(selector)
        if i < 0 or i >= len(ps):
            raise ValueError('Port index out of range')
        return ps[i]
    matches = [p for p in ps if selector in (p.Name, p.NickName)]
    if len(matches) != 1:
        raise ValueError('Port selector missing or ambiguous: {}'.format(selector))
    return matches[0]


def copy_input_defaults(param, relay):
    """A new source overrides persistent input data; carry that data to the relay."""
    data = getattr(param, 'PersistentData', None)
    if data is None:
        return
    for path in data.Paths:
        relay.PersistentData.EnsurePath(path)
        for item in data.get_Branch(path):
            relay.PersistentData.Append(item.Duplicate() if item is not None else None, path)


def document():
    import Grasshopper as GH
    canvas = GH.Instances.ActiveCanvas
    if canvas is None or canvas.Document is None:
        raise ValueError('No active Grasshopper document')
    return canvas.Document


def snapshot(doc):
    from System import Convert
    objects, wires = [], []
    for obj in doc.Objects:
        obj.Attributes.PerformLayout()
        a, b = obj.Attributes, obj.Attributes.Bounds
        data = dict(guid=str(obj.InstanceGuid), name=obj.Name, nickname=obj.NickName,
                    category=obj.Category, subcategory=obj.SubCategory,
                    x=float(a.Pivot.X), y=float(a.Pivot.Y), width=float(b.Width), height=float(b.Height),
                    bounds=dict(x=float(b.X), y=float(b.Y), width=float(b.Width), height=float(b.Height)),
                    inputs=port_info(obj, 'inputs'), outputs=port_info(obj, 'outputs'),
                    type='group' if obj.GetType().Name == 'GH_Group' else 'component')
        objects.append(data)
        kind = obj.GetType().Name
        data['type'] = next((label for token, label in (
            ('Slider', 'slider'), ('Panel', 'panel'), ('Toggle', 'toggle'),
            ('Group', 'group'), ('Relay', 'relay'), ('Param', 'param')) if token in kind),
            'param' if obj.Category == 'Params' else 'component')
        data['input_count'], data['output_count'] = len(data['inputs']), len(data['outputs'])
        if hasattr(obj, 'Slider'):
            data.update(value=Convert.ToDouble(obj.Slider.Value), min=Convert.ToDouble(obj.Slider.Minimum), max=Convert.ToDouble(obj.Slider.Maximum))
        elif hasattr(obj, 'UserText'):
            data['value'] = (obj.UserText or '')[:100]
        for i, p in enumerate(params(obj, 'inputs')):
            for source in p.Sources:
                owner = source.Attributes.GetTopLevel.DocObject
                outputs = params(owner, 'outputs')
                wires.append(dict(source_guid=str(owner.InstanceGuid), target_guid=str(obj.InstanceGuid),
                                  source_output_idx=outputs.index(source), target_input_idx=i))
    revision = hashlib.sha256(json.dumps({'objects': objects, 'wires': wires},
                                        sort_keys=True).encode('utf-8')).hexdigest()
    return dict(success=True, components=objects, wires=wires, component_count=len(objects), revision=revision,
                file_path=doc.FilePath or '', is_modified=doc.IsModified)


def apply_graph(sliders, components, wires, solve=True, replace=True, include_deprecated=False):
    import System
    import System.Drawing as SD
    from Grasshopper.Kernel.Special import GH_NumberSlider
    from Grasshopper.GUI.Base import GH_SliderAccuracy
    doc = document()
    staged, connections = {}, []
    # Preflight everything before attaching anything to the active document.
    for spec in sliders + components:
        key = spec['key']
        if not key or key in staged:
            raise ValueError('Empty or duplicate graph key: {}'.format(key))
        if not all(math.isfinite(float(spec[k])) for k in ('x', 'y')):
            raise ValueError('Non-finite component position')
        if 'selector' in spec:
            obj = resolve(spec['selector'], include_deprecated).CreateInstance()
        else:
            lo, value, hi = [float(spec[k]) for k in ('min', 'value', 'max')]
            if not all(math.isfinite(v) for v in (lo, value, hi)) or not lo <= value <= hi or lo == hi:
                raise ValueError('Slider requires finite min <= value <= max and min < max')
            obj = GH_NumberSlider()
            accuracy = {'float': GH_SliderAccuracy.Float, 'int': GH_SliderAccuracy.Integer,
                        'even': GH_SliderAccuracy.Even, 'odd': GH_SliderAccuracy.Odd}
            obj.Slider.Type = accuracy[spec.get('type', 'float')]
            obj.Slider.Minimum, obj.Slider.Maximum = System.Decimal(lo), System.Decimal(hi)
            obj.Slider.Value = System.Decimal(value)
        if obj is None or bool(getattr(obj, 'Obsolete', False)):
            raise ValueError('Unavailable or obsolete component')
        obj.CreateAttributes()
        obj.Attributes.Pivot = SD.PointF(float(spec['x']), float(spec['y']))
        obj.NickName = spec.get('nickname') or spec.get('name') or obj.NickName or key
        staged[key] = obj
    adjacency = {k: [] for k in staged}
    for w in wires:
        s, t = w['src_key'], w['dst_key']
        connections.append((port(staged[s], 'outputs', w['src']), port(staged[t], 'inputs', w['dst'])))
        adjacency[s].append(t)
    visiting, done = set(), set()
    def visit(k):
        if k in visiting:
            raise ValueError('Graph contains a cycle')
        if k in done:
            return
        visiting.add(k)
        for t in adjacency[k]:
            visit(t)
        visiting.remove(k)
        done.add(k)
    for k in staged:
        visit(k)
    # Descriptions are real tree-preserving parameters, not renamed components.
    relays, input_relays, output_relays = [], {}, {}
    connected_inputs = {str(t.InstanceGuid) for _, t in connections}
    for obj in list(staged.values()):
        obj.Attributes.PerformLayout()
        if str(obj.ComponentGuid).lower() == DESCRIPTION:
            name_view(obj)
            continue
        if not hasattr(obj, 'Params'):
            continue
        for side in ('inputs', 'outputs'):
            for p in params(obj, side):
                relay = resolve(DESCRIPTION).CreateInstance()
                relay.CreateAttributes()
                name_view(relay)
                relay.NickName = p.NickName or p.Name
                relay.Description = '{}: {}'.format(obj.NickName, p.Description or p.Name)
                if side == 'inputs' and str(p.InstanceGuid) not in connected_inputs:
                    copy_input_defaults(p, relay)
                point = p.Attributes.InputGrip if side == 'inputs' else p.Attributes.OutputGrip
                relay.Attributes.Pivot = SD.PointF(point.X + (-140 if side == 'inputs' else 140), point.Y)
                relays.append(relay)
                (input_relays if side == 'inputs' else output_relays)[str(p.InstanceGuid)] = relay
    routed = [(output_relays.get(str(s.InstanceGuid), s), input_relays.get(str(t.InstanceGuid), t))
              for s, t in connections]
    for obj in staged.values():
        for p in params(obj, 'inputs'):
            if str(p.InstanceGuid) in input_relays:
                routed.append((input_relays[str(p.InstanceGuid)], p))
        for p in params(obj, 'outputs'):
            if str(p.InstanceGuid) in output_relays:
                routed.append((p, output_relays[str(p.InstanceGuid)]))
    added = []
    try:
        for obj in list(staged.values()) + relays:
            doc.AddObject(obj, False)
            added.append(obj)
        for s, t in routed:
            t.AddSource(s)
        if solve:
            doc.NewSolution(False)
        from Grasshopper.Kernel import GH_RuntimeMessageLevel
        diagnostics = []
        for obj in staged.values():
            if hasattr(obj, 'RuntimeMessages'):
                for level in (GH_RuntimeMessageLevel.Warning, GH_RuntimeMessageLevel.Error):
                    diagnostics.extend({'guid': str(obj.InstanceGuid), 'level': str(level), 'text': str(msg)}
                                       for msg in obj.RuntimeMessages(level))
        return {'success': True, 'placed': [{'key': k, 'guid': str(o.InstanceGuid)} for k, o in staged.items()],
                'wires_ok': len(connections), 'description_guids': [str(o.InstanceGuid) for o in relays],
                'solve_requested': solve, 'document_enabled': doc.Enabled, 'diagnostics': diagnostics}
    except Exception:
        for obj in reversed(added):
            doc.RemoveObject(obj, False)
        raise


def move_many(moves, layout_options=None, expected_revision=None):
    import System
    import System.Drawing as SD
    doc = document()
    if expected_revision is not None and snapshot(doc)['revision'] != expected_revision:
        raise ValueError('Canvas changed since planning; request a fresh layout')
    if not moves:
        return {'success': True, 'components_moved': 0, 'descriptions_normalized': 0}
    staged, seen = [], set()
    for m in moves:
        if not all(math.isfinite(float(m[k])) for k in ('old_x', 'old_y', 'new_x', 'new_y')):
            raise ValueError('Non-finite move')
        if m['guid'] in seen:
            raise ValueError('Duplicate move GUID')
        seen.add(m['guid'])
        obj = doc.FindObject(System.Guid(m['guid']), False)
        if obj is None:
            raise ValueError('Component no longer exists')
        p = obj.Attributes.Pivot
        if abs(p.X - m['old_x']) > .01 or abs(p.Y - m['old_y']) > .01:
            raise ValueError('Canvas changed since planning; request a fresh layout')
        if not all(math.isfinite(float(m[k])) for k in ('new_x', 'new_y')):
            raise ValueError('Non-finite move')
        staged.append((obj, p, SD.PointF(float(m['new_x']), float(m['new_y']))))
    if layout_options is not None:
        all_nodes = {str(o.InstanceGuid) for o in doc.Objects if o.GetType().Name != 'GH_Group'}
        if seen != all_nodes:
            raise ValueError('Full layout must include every current non-group object')
    descriptions = []
    for obj in doc.Objects:
        if str(obj.InstanceGuid) in seen and str(obj.ComponentGuid).lower() == DESCRIPTION:
            descriptions.append((obj, obj.Name, obj.IconDisplayMode))
    try:
        normalized = 0
        for obj, old_name, old_mode in descriptions:
            name_view(obj)
            if obj.Name != old_name or obj.IconDisplayMode != old_mode:
                normalized += 1
            obj.Attributes.ExpireLayout()
        replanned = None
        if normalized and layout_options is not None:
            # Name View can change measured widths. Replan before assigning pivots.
            import importlib.util
            import os
            path = os.path.join(os.path.dirname(__file__), '..', 'rhino_grasshopper_mcp', 'port_layout.py')
            spec = importlib.util.spec_from_file_location('rhino_port_layout', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            state = snapshot(doc)
            replanned = module.calculate_layout(state['components'], state['wires'], **layout_options)
            if not replanned['success']:
                raise ValueError(replanned['error'])
            targets = {m['guid']: m for m in replanned['moves']}
            staged = [(obj, old, SD.PointF(targets[str(obj.InstanceGuid)]['new_x'],
                                         targets[str(obj.InstanceGuid)]['new_y'])) for obj, old, new in staged]
        for obj, old, new in staged:
            obj.Attributes.Pivot = new
            obj.Attributes.ExpireLayout()
        for obj in doc.Objects:
            obj.Attributes.ExpireLayout()
        result = {'success': True, 'components_moved': len(staged), 'descriptions_normalized': normalized}
        if replanned:
            result['metrics'] = replanned['metrics']
            result['replanned_for_name_view'] = True
        return result
    except Exception:
        for obj, old, new in staged:
            obj.Attributes.Pivot = old
            obj.Attributes.ExpireLayout()
        for obj, old_name, old_mode in descriptions:
            obj.Name, obj.IconDisplayMode = old_name, old_mode
            obj.Attributes.ExpireLayout()
        raise

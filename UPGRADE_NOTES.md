# Grasshopper graph and layout upgrade

## Comparison baseline

Reviewed McNeel RhinoAI **plugin-v0.3.0**, the installed version, rather than
assuming its current development branch matches the installed plugin:

- [Apply graph](https://github.com/mcneel/RhinoAI/blob/plugin-v0.3.0/rhino/plugin/Tools/GH1/GH1_ApplyGraphTool.cs): keyed batch placement, named/indexed ports, cycle checks, solve diagnostics. Its implementation reports partial failures; it does not roll back the whole graph.
- [Canvas graph](https://github.com/mcneel/RhinoAI/blob/plugin-v0.3.0/rhino/plugin/Tools/GH1/GH1_GetCanvasGraphTool.cs): structured objects, ports, connections and runtime messages.
- [Scripting workflow](https://github.com/mcneel/RhinoAI/blob/plugin-v0.3.0/cc-plugin/agents/grasshopper-scripter.md): inspect, search, describe, build in batches, then solve.

These files do not implement an ML canvas layout engine. The comparison here is
to their graph editing workflow, not a claim to have reproduced a McNeel ML model.

## Changes

- `gh_search_components`, `gh_describe_component`, `gh_apply_graph` now have live
  listener implementations. Names must resolve uniquely; GUIDs are preferred.
  Obsolete proxies are rejected even by GUID. `include_deprecated` is retained
  for compatibility but only permits hidden, non-obsolete proxies.
- Generic Python selectors resolve to Rhino 8 Python 3 Script
  (`719467e6-7cf5-4848-99b0-c5dd57e5442c`). No legacy Python substitution.
- Batch creation validates keys, ports, ranges and cycles before insertion.
  Insertion failures remove newly added objects. No existing objects are replaced;
  `replace` is a compatibility argument because all keyed objects are newly created.
- New component ports receive Elefront EF Data Description (R6) parameters in
  Name View. Their plugin-default Name comes from a fresh instance; NickName holds
  the port label, and Description explains the port. Elefront must be installed.
  This does not edit Sunglasses settings.
- `ml_auto_layout` uses measured input/output grips and actual bounds, ranks the
  graph, brings short branches closer to consumers, and optimizes vertical port
  error without overlapping same-column boxes. Learned spacing remains an input.
  Groups are not moved as nodes. No wires, persistent data or tree settings are
  rewritten by layout. Existing component types are not migrated by layout.
- Layout reports horizontal wires, mean vertical port error and any estimated
  ports. `dry_run=true` returns proposed moves. Applying validates every original
  position before moving anything; failed assignments restore original pivots.
  Existing Elefront descriptions are restored to their plugin-default Name and
  Name View when applying layout. If that changes bounds, positions are recalculated
  and the result includes `replanned_for_name_view` and revised metrics. Dry run
  does not change display settings and therefore previews the current display mode.
- MCP socket calls run off the asyncio event loop, serialize per bridge, and close
  sockets on failure. UI-thread timeout no longer reruns the mutation off-thread.
- Zero-valued ML coordinates are retained; independent learners no longer share
  nested default preferences.

## Validation

Run `python -B -m unittest discover -s tests -v` from this repository.
Eleven tests cover measured port alignment, spacing, cycles, missing endpoints,
non-finite coordinates, deterministic ordering, groups, input-default tree copying,
empty moves, stale canvas revisions and a real Rhino fixture.

Run `tests/live_smoke.py` in **Rhino 8 Python 3** for a detached-document test.
It creates 11 objects with seven Elefront descriptions and ten wires, computes
`2 + 3 -> Python 3 x 2 = 10`, applies layout, verifies the wires and output are
unchanged, and tests invalid creation and stale-position rejection. The document
is disposed in `finally`; the user's active definition is not replaced.

The committed measured fixture improved mean vertical port error from **14 to
10 canvas units** versus `calculate_auto_layout_v1`, with **6/10 horizontal wires**
and no estimated ports. This is a small regression fixture, not proof of parity
on large production definitions. Collision spacing can prevent every fan-in or
fan-out wire from becoming horizontal. Cyclic definitions are rejected, not laid
out heuristically. Large-canvas visual review and crossing minimization remain
areas for further benchmarking.

The MCP handler-to-TCP-listener path was also exercised on an isolated test port:
search, describe, batch graph creation, layout dry run and layout application.

`tests/live_defaults.py` additionally verifies in a detached Rhino document that
`2 + default 7 = 9` survives automatic relay insertion, typed values and empty
branches retain their tree paths, and changed wiring invalidates a planned move.

The final review added preservation of persistent input defaults when inserting
description relays (including branch paths and empty branches), a canvas revision
check before applying layout, and validation of original as well as target move
coordinates. Empty move requests now leave all descriptions unchanged; partial
moves only normalize included objects, and a full replan requires the whole
non-group canvas. Live smoke testing does not rewrite the committed fixture unless
explicitly run with `UPDATE_FIXTURE=True`.

## Running the upgraded version

Keep the repository folder structure when updating: the listener needs
`rhino_listener/graph_operations.py` and the sibling package's `port_layout.py`.
Restart the
custom listener and its MCP client process after updating code. These changes do
not replace McNeel's RhinoAI plugin or its working Codex launcher. Public GitHub
publication is separate from this local working-tree update.

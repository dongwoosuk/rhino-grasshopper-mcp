"""
Joseki corpus search — the knowledge layer of this MCP server.

Reads the parsed corpus produced by the Kifu Narabe pipeline:
    Source/graph_json/registry.json   identity + servable/packaged flags
    Source/graph_json/cards/*.card.md algorithm cards
    Source/graph_json/moves.json     move index (기법 단위)
    Source/graph_json/digests/*.md    3 KB condensed graph summaries

Read-only. Nothing here touches the kifu (original .gh files).

The loader lives in src/gh/gh_joseki/joseki_core.py and is shared with the Eto
palette and the GH canvas component. It used to be duplicated here, and the copy
silently lacked source-path resolution for pure-Python cards (calpoly_*), which
have no registry entry -- so this module reported "원본 없음" for them. One loader,
one behaviour.
"""
import glob
import os
import sys

_CORE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "..", "..", "src", "gh", "gh_joseki"))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import joseki_core as _core  # noqa: E402

load = _core.load
_score = _core._score
_corpus_dir = _core.corpus_dir


def stats():
    d = load()
    from collections import Counter
    tc = Counter(t for c in d["cards"] for t in c["tags"])
    return {
        "definitions": len(d["registry"]),
        # the index also carries uncarded definitions, searchable via their digest
        "searchable": len(d["cards"]),
        "cards": sum(1 for c in d["cards"] if c.get("has_card")),
        "digest_only": sum(1 for c in d["cards"] if not c.get("has_card")),
        "moves": len(d["moves"]),
        "servable": sum(1 for c in d["cards"] if c["servable"]),
        "packaged": sum(1 for c in d["cards"] if c["packaged"]),
        "top_tags": tc.most_common(20),
    }


def _kind(source_path):
    p = (source_path or "").lower()
    return "gh" if p.endswith((".gh", ".ghx")) else ("python" if p.endswith(".py") else "unknown")


def search(query=None, move=None, tag=None, servable=False, packaged=False,
           grade=None, dep=None, hide_flagged=False, limit=8):
    """Search definitions or the move index. Returns a JSON-serializable dict.

    grade filters by provenance (practice / edu / reference / vendor) -- the audit
    found tutorial and reference material dominates the move index, so 'practice'
    is the filter that raises signal.
    """
    f = dict(grade=grade, dep=dep, hide_flagged=hide_flagged,
             servable=servable, packaged=packaged)

    if move:
        rows = _core.search_moves(move, limit=100000, **f)
        return {
            "mode": "move",
            "query": move,
            "filters": f,
            "total": len(rows),
            "results": [{
                "score": m["score"],
                "move": m["move"],
                "definition": m["definition"],
                "grade": m["grade"],
                "kind": _kind(m.get("source_path")),
                "source_path": m.get("source_path"),
            } for m in rows[:limit]],
        }

    rows = _core.search_definitions(query or "", tag=tag, limit=100000, **f)
    return {
        "mode": "definition",
        "query": query,
        "filters": dict(tag=tag, **f),
        "total": len(rows),
        "results": [{
            "score": c["score"],
            "name": c["name"],
            "intent": c["intent"],
            "algorithm": c["algo"] or None,
            "status": c["status"] or None,
            "tags": c["tags"],
            "moves": c["moves"][:3],
            "deps": c["deps"],
            "grade": c["grade"],
            "has_card": c.get("has_card", True),
            "flagged": c["flagged"],
            "servable": c["servable"],
            "packaged": c["packaged"],
            "kind": _kind(c["source_path"]),
            "source_path": c["source_path"],
        } for c in rows[:limit]],
    }


def show(name, digest=False):
    """Full card text (default) or the 3 KB digest for one definition."""
    root = _corpus_dir()
    if digest:
        hits = sorted(glob.glob(os.path.join(root, "digests", f"*{name}*.md")))
        if not hits:
            return {"found": False, "name": name}
        return {"found": True, "kind": "digest",
                "file": os.path.basename(hits[0]),
                "text": open(hits[0], encoding="utf-8").read()}
    d = load()
    hits = [c for c in d["cards"] if name.lower() in c["name"].lower()]
    if not hits:
        return {"found": False, "name": name}
    c = hits[0]
    return {"found": True, "kind": "card", "name": c["name"],
            "form": _kind(c["source_path"]),
            "source_path": c["source_path"], "text": c["body"],
            "alternatives": [x["name"] for x in hits[1:5]]}

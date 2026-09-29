"""Which assumptions can a two-path gate not test? List what both paths share.

A reviewer asked how to decide which semantic assumptions in a large pipeline need an
independent check. For a redundancy gate the mechanical part of the answer is the set
of definitions both paths depend on: anything upstream of both is compared with
itself. This script computes that set for the SORO gate from the source, at the
pre-correction commit and at the current one, by intersecting the names each path
imports from pipeline modules, and reports which shared names are vocabularies
(set-valued constants that map source codes to meanings) rather than loaders.

Path A is governance_report.python_side (Python counts). Path B is build_graph.py,
whose output graph the SPARQL side queries. The SPARQL queries add no vocabulary of
their own: they count nodes by defect class, and build_graph.py decides class
membership.

Run: python3 paper/gates/shared_ancestor_audit.py
"""
import ast
import json
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def source(rev, path):
    if rev is None:
        return (ROOT / path).read_text()
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def imported_from_reconcile(src):
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module == "reconcile":
            names |= {a.name for a in node.names}
    return names


def kinds(src_reconcile):
    out = {}
    for node in ast.parse(src_reconcile).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Set, ast.Name)):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = "vocabulary" if isinstance(node.value, ast.Set) else "alias"
        elif isinstance(node, ast.FunctionDef):
            out[node.name] = "function"
    return out


def audit(rev):
    a = imported_from_reconcile(source(rev, "pipeline/governance_report.py"))
    b = imported_from_reconcile(source(rev, "pipeline/build_graph.py"))
    k = kinds(source(rev, "pipeline/reconcile.py"))
    shared = sorted(a & b)
    return {"path_A_imports": sorted(a), "path_B_imports": sorted(b), "shared": shared,
            "shared_vocabularies": [n for n in shared if k.get(n) == "vocabulary"],
            "shared_functions": [n for n in shared if k.get(n) == "function"]}


if __name__ == "__main__":
    print(json.dumps({"pre_correction_24d684e": audit("24d684e"), "current": audit(None)},
                     indent=2))

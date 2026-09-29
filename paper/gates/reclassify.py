# SUPERSEDED (29 Sep 2026): regex labels describe vocabulary, not behaviour. The paper
# uses behaviour_probe.py / label_trials.py. Its "H1" reading (E and C are destruction)
# is itself a misreading; see history_check.py.
"""Reclassify the reuse trials on the variable that actually matters.

The first classifier asked whether the generated second path IMPORTED the shared
constants or RESTATED them. That turns out to be the wrong question. Trials that
restate copy the defective vocabulary verbatim under a new name, so they are
textually independent and semantically identical.

The variable that matters is whether the generated path INHERITS THE DEFECT. The
defect has two halves, both visible in the constants:
  H1  E (exploded) and C (collided) are absent from the "gone" vocabulary, so a
      destroyed object is treated as still in orbit.
  H2  the transition codes DK, ATT, TFR, GRP are not excluded, so phases that end
      because the object joined another object are counted as disposition claims.

A second path is only genuinely independent if it fixes at least one of these, which
requires going to the source's documentation rather than to the code in front of it.

Run: python3 paper/gates/reclassify.py
Writes: paper/gates/reuse_final.json
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
RAW = HERE / "reuse_raw"

CONST_NAMES = ["GONE", "INORBIT", "LEFT_EARTH", "ERROR", "LOST"]
TRANSITION = ["DK", "ATT", "TFR", "GRP"]


def strip_fences(t):
    return re.sub(r"^```[a-z]*\n|```$", "", t.strip(), flags=re.M)


def analyse(code):
    code = strip_fences(code)

    imports_shared = bool(re.search(
        r"(?:from|import)\s+[\w.]*reconcile[\w.]*\s+import\s+[^\n]*"
        r"(?:GONE|INORBIT|LEFT_EARTH|ERROR|LOST)", code))

    # any set/frozenset/list literal of status codes, under ANY variable name
    literal_blocks = re.findall(
        r"=\s*(?:frozenset\s*\(\s*)?[{\[\(]([^}\])]*)[}\])]", code, re.S)
    own_vocab = [b for b in literal_blocks
                 if len(re.findall(r'["\']([A-Z][A-Z ]{0,6})["\']', b)) >= 4]
    restates = len(own_vocab) > 0

    pooled = " ".join(own_vocab)
    # H1: is a destruction code present in any vocabulary the code defines?
    fixes_h1 = bool(re.search(r'["\']E["\']', pooled)) and \
        bool(re.search(r'["\']C["\']', pooled))
    # H2: are the transition codes named anywhere at all, in code or comment?
    names_transition = sum(1 for t in TRANSITION if re.search(rf'["\']{t}["\']', code))
    fixes_h2 = names_transition >= 2

    # A bare reference to a constant the snippet never defines is the strongest
    # form of reuse: the code simply assumes the shared vocabulary is in scope.
    defines_named = {c for c in CONST_NAMES
                     if re.search(rf"^\s*{c}\s*=", code, re.M)}
    refs_named = {c for c in CONST_NAMES if re.search(rf"\b{c}\b", code)}
    bare_reference = bool(refs_named - defines_named) and not imports_shared

    if imports_shared:
        vocabulary_source = "imported from the shared module"
    elif bare_reference:
        vocabulary_source = "referenced bare, assumed in scope"
    elif restates:
        vocabulary_source = "copied into a new literal"
    else:
        vocabulary_source = "no vocabulary present"

    inherits = not (fixes_h1 or fixes_h2)
    return {
        "imports_shared": imports_shared,
        "bare_reference": bare_reference,
        "shares_by_reference": imports_shared or bare_reference,
        "restates_own_literal": restates,
        "vocabulary_source": vocabulary_source,
        "fixes_H1_destruction_codes": fixes_h1,
        "fixes_H2_transition_codes": fixes_h2,
        "INHERITS_DEFECT": inherits,
    }


def main():
    rows = []
    for f in sorted(RAW.glob("*.txt")):
        cond, model, i = f.stem.rsplit("_", 2)
        t = f.read_text()
        if t.startswith("__TRIAL_ERROR__") or not t.strip():
            continue
        r = analyse(t)
        r.update(condition=cond, model=model, trial=int(i))
        rows.append(r)

    summary = {}
    for cond in ["neutral", "independent", "explicit"]:
        sel = [r for r in rows if r["condition"] == cond]
        if not sel:
            continue
        summary[cond] = {
            "n": len(sel),
            "shares_by_reference": sum(r["shares_by_reference"] for r in sel),
            "restates_own_literal": sum(r["restates_own_literal"] for r in sel),
            "inherits_defect": sum(r["INHERITS_DEFECT"] for r in sel),
        }
    summary["ALL"] = {
        "n": len(rows),
        "shares_by_reference": sum(r["shares_by_reference"] for r in rows),
        "restates_own_literal": sum(r["restates_own_literal"] for r in rows),
        "inherits_defect": sum(r["INHERITS_DEFECT"] for r in rows),
    }

    (HERE / "reuse_final.json").write_text(
        json.dumps({"summary": summary, "trials": rows}, indent=2))

    print(f"{'condition':14}{'n':>4}{'shares ref':>12}{'restates':>10}{'inherits defect':>17}")
    for k, v in summary.items():
        print(f"{k:14}{v['n']:>4}{v['shares_by_reference']:>12}"
              f"{v['restates_own_literal']:>10}{v['inherits_defect']:>17}")


if __name__ == "__main__":
    main()

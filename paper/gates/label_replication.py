"""Behavioural labels for the controlled replication (replication_raw/).

Run: python3 paper/gates/label_replication.py paper/gates/replication_raw paper/gates/replication_labels.json
"""
import sys, json, collections, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import behaviour_probe as B
if __name__=="__main__":
    d=pathlib.Path(sys.argv[1])
    ref=B.probe((d/"SHOWN_PATH.py").read_text())["signature"]
    print("ref",ref)
    rows=[]
    for f in sorted(p for p in d.glob("*__*__*.txt") if not p.name.startswith("PROMPT")):
        cond,model,i=f.stem.split("__")
        t=f.read_text()
        if t.startswith("__TRIAL_ERROR__"): rows.append((cond,model,i,"trial error",None,None)); continue
        r=B.probe(t)
        lab=r["status"]; pc=r.get("per_code"); real=None
        if lab=="ok":
            lab="identical" if r["signature"]==ref else "differs"
            real=B.real_count(t,r["source_fns"])
        elif lab!="does not run":
            fns=[c["fn"] for c in r["raw"]["calls"] if "returned" in c]
            real=B.real_count(t,fns) if fns else None
        det=None if lab in("identical","differs") else (r.get("raw") or {}).get("exec_error") or str((r.get("raw") or {}).get("calls"))[:200]
        rows.append((cond,model,i,lab,pc,real,det))
        print(cond,model[:14],i,lab,json.dumps(pc) if lab=="differs" else "",real, det or "")
    c=collections.Counter((r[0],r[3]) for r in rows)
    for k in sorted(c): print(c[k],k)
    json.dump(rows,open(sys.argv[2],"w"))

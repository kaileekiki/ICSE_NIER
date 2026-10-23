#!/usr/bin/env python3
"""Create a surgical Go test-ablation task JSONL using the official image."""
from __future__ import annotations
import argparse, json, pathlib, subprocess, tempfile, uuid

def run(cmd, **kw): return subprocess.run(cmd, check=True, text=True, **kw)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--task",required=True); ap.add_argument("--test-name",required=True)
    ap.add_argument("--test-id",required=True); ap.add_argument("--output",required=True)
    a=ap.parse_args(); task=json.loads(pathlib.Path(a.task).read_text().splitlines()[0])
    name="who-exam-prep-"+uuid.uuid4().hex[:10]; image=task["docker_image"]
    run(["docker","pull",image]); run(["docker","run","-d","--name",name,image,"sleep","infinity"],stdout=subprocess.DEVNULL)
    try:
        with tempfile.TemporaryDirectory() as td:
            td=pathlib.Path(td); patch=td/"test.patch"; patch.write_text(task["test_patch"],encoding="utf-8")
            run(["docker","cp",str(patch),f"{name}:/tmp/test.patch"])
            run(["docker","exec",name,"sh","-lc","cd /testbed; [ -d .git ] || cd $(dirname $(find . -maxdepth 3 -name .git -print -quit)); git apply /tmp/test.patch"])
            locate=run(["docker","exec",name,"sh","-lc",f"cd /testbed; grep -R -l --include='*_test.go' '^func {a.test_name}(' . | head -1"],capture_output=True).stdout.strip()
            if not locate: raise RuntimeError("test function not found after applying original test_patch")
            host=td/"target.go"; run(["docker","cp",f"{name}:/testbed/{locate.removeprefix('./')}",str(host)])
            run(["python3",str(pathlib.Path(__file__).with_name("remove_go_test.py")),str(host),a.test_name])
            run(["docker","cp",str(host),f"{name}:/testbed/{locate.removeprefix('./')}"])
            diff=run(["docker","exec",name,"sh","-lc","cd /testbed; git diff --binary HEAD"],capture_output=True).stdout
        task["test_patch"]=diff
        for key in ("FAIL_TO_PASS","PASS_TO_PASS"):
            task[key]=[x for x in task[key] if x!=a.test_id]
        pathlib.Path(a.output).write_text(json.dumps(task,ensure_ascii=False)+"\n",encoding="utf-8")
    finally:
        subprocess.run(["docker","rm","-f",name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if __name__=="__main__": main()

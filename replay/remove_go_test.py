#!/usr/bin/env python3
"""Surgically remove one top-level Go test function using a lexical brace scan."""
from __future__ import annotations
import argparse, pathlib, re

def end_brace(text: str, start: int) -> int:
    depth=0; i=start; state="code"
    while i < len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ""
        if state=="code":
            if c=='/' and n=='/': state="line"; i+=2; continue
            if c=='/' and n=='*': state="block"; i+=2; continue
            if c=='"': state="string"; i+=1; continue
            if c=="'": state="rune"; i+=1; continue
            if c=='`': state="raw"; i+=1; continue
            if c=='{': depth+=1
            elif c=='}':
                depth-=1
                if depth==0: return i+1
        elif state=="line":
            if c=='\n': state="code"
        elif state=="block":
            if c=='*' and n=='/': state="code"; i+=2; continue
        elif state in ("string","rune"):
            if c=='\\': i+=2; continue
            if (state=="string" and c=='"') or (state=="rune" and c=="'"): state="code"
        elif state=="raw" and c=='`': state="code"
        i+=1
    raise ValueError("unbalanced function braces")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("path"); ap.add_argument("test_name"); a=ap.parse_args()
    p=pathlib.Path(a.path); text=p.read_text(encoding="utf-8")
    match=re.search(rf"(?m)^func\s+{re.escape(a.test_name)}\s*\([^)]*\)[^{{]*\{{",text)
    if not match: raise SystemExit(f"function not found: {a.test_name}")
    start=match.start(); brace=text.find("{",match.start(),match.end()); end=end_brace(text,brace)
    while end<len(text) and text[end] in " \t": end+=1
    if end<len(text) and text[end]=='\n': end+=1
    p.write_text(text[:start]+text[end:],encoding="utf-8")
    print(f"removed {a.test_name} from {p}")
if __name__=="__main__": main()

#!/usr/bin/env python3
"""Decompress one Position.z line from live.jsonl and print structure."""
import json
import base64
import zlib
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "live.jsonl"
found = False
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("Type") != "Position.z":
            continue
        payload = o.get("Json")
        if not isinstance(payload, str):
            print("Json is not a string:", type(payload))
            found = True
            break
        raw = base64.b64decode(payload)
        # F1 uses raw deflate (no zlib header)
        out = zlib.decompress(raw, -zlib.MAX_WBITS)
        data = json.loads(out.decode("utf-8"))
        print("Top-level keys:", list(data.keys()))
        pos = data.get("Position") or data.get("position") or data
        if isinstance(pos, dict):
            for drv, v in list(pos.items())[:2]:
                print(f"  Driver {drv}:", v)
        else:
            print("  Raw:", str(data)[:500])
        found = True
        break
if not found:
    print("No Position.z line found")

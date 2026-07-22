"""Print top-level field -> python type for each captured runtime sample."""
import json

samples = json.load(open("/app/backend/tools/runtime_samples.json"))


def pytype(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        inner = pytype(v[0]) if v else "?"
        return f"list[{inner}]"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


for name in sorted(samples):
    s = samples[name]
    if s.get("status") != 200 or not isinstance(s.get("sample"), dict):
        print(f"\n### {name}  status={s.get('status')} (not dict)")
        continue
    print(f"\n### {name}")
    for k, v in s["sample"].items():
        t = pytype(v)
        extra = ""
        if isinstance(v, dict):
            extra = " keys=" + str(list(v.keys())[:12])
        if isinstance(v, list) and v and isinstance(v[0], dict):
            extra = " item_keys=" + str(list(v[0].keys())[:14])
        print(f"  {k}: {t}{extra}")

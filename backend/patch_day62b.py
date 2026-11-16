import json
from pathlib import Path

report = Path("analysis/day62_template_report.py")
s = report.read_text()
if "describe(strategy.long)" not in s:
    s = s.replace("from analysis.rule_builder import build_strategy\n", "from analysis.rule_builder import build_strategy\nfrom analysis.rules import describe\n")
    s = s.replace("count = log.record(strategy_key(strategy), symbol, strategy.name)[\"count\"]",
                  "count = log.record(strategy_key(strategy), symbol, strategy.name, describe(strategy.long) if strategy.long else None, describe(strategy.short) if strategy.short else None)[\"count\"]")
    report.write_text(s)
    print("report patched")
else:
    print("report already patched")

from analysis.rule_builder import build_strategy
from analysis.evidence import strategy_key
from analysis.rules import describe
from analysis.templates import TEMPLATES
from analysis.trial_log import DEFAULT_PATH

texts = {}
for t in TEMPLATES.values():
    st = build_strategy(t["strategy"])
    texts[strategy_key(st)] = (describe(st.long) if st.long else None, describe(st.short) if st.short else None)
if DEFAULT_PATH.exists():
    lines, fixed = [], 0
    for line in DEFAULT_PATH.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            lines.append(line)
            continue
        if isinstance(row, dict) and row.get("long") is None and row.get("short") is None and row.get("key") in texts:
            row["long"], row["short"] = texts[row["key"]]
            fixed += 1
        lines.append(json.dumps(row))
    DEFAULT_PATH.write_text("\n".join(lines) + "\n")
    print(f"trial log: filled in the text of {fixed} entries")
else:
    print("no trial log yet, nothing to fill")

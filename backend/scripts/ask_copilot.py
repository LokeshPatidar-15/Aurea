import sys

from services import copilot_service

if len(sys.argv) < 2:
    print('usage: python3 -m scripts.ask_copilot "your question"')
    sys.exit(1)
try:
    r = copilot_service.ask(" ".join(sys.argv[1:]))
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(1)
print(f"[{r['mode']} | confidence {r['confidence']} | coverage {r['coverage']}]")
print(r["answer"])
for s in r["sources"]:
    print(f"  [{s['n']}]{'*' if s['cited'] else ' '} {s['doc']} > {s['title']}")
if r["llm_error"] or r["fallback_reason"]:
    print(f"  note: llm_error={r['llm_error']} fallback_reason={r['fallback_reason']}")

from pathlib import Path

path = Path(__file__).parent / "analysis" / "day64_checks.py"
text = path.read_text()
if "got_first" in text:
    print("already patched")
else:
    old1 = "    hub.publish(tick(ts=NOW_MS))\n    res = await asyncio.wait_for(ts_, 3)\n"
    new1 = "    hub.publish(tick(ts=NOW_MS))\n    await settle()\n    got_first = len(fast.ticks()) == 1\n    res = await asyncio.wait_for(ts_, 3)\n"
    old2 = 'check("one stuck client never blocks the others", len(fast.ticks()) == 2)'
    new2 = 'check("one stuck client never blocks the others", got_first and len(fast.ticks()) == 2)'
    assert old1 in text and old2 in text, "expected text not found, send me analysis/day64_checks.py"
    path.write_text(text.replace(old1, new1, 1).replace(old2, new2, 1))
    print("patched")

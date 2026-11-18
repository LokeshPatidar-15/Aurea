from pathlib import Path

ROOT = Path(__file__).parent
path = ROOT / "main.py"
text = path.read_text()
if "portfolio_router" in text:
    print("main.py: already patched")
else:
    pairs = [
        ("from routers import pipeline as pipeline_router\n", "from routers import pipeline as pipeline_router\nfrom routers import portfolio as portfolio_router\n"),
        ("app.include_router(pipeline_router.router)\n", "app.include_router(pipeline_router.router)\napp.include_router(portfolio_router.router)\n"),
    ]
    for old, new in pairs:
        assert old in text, f"main.py: expected text not found: {old[:50]!r}. Send me main.py"
        text = text.replace(old, new, 1)
    path.write_text(text)
    print("main.py: patched")

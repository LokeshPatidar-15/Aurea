import json
from pathlib import Path


def status(code):
    return f'pm.test("Status is {code}", function () {{ pm.response.to.have.status({code}); }});'


def check(name, body):
    return f'pm.test("{name}", function () {{ {body} }});'


def request(name, method, path, tests, body=None):
    req = {"method": method, "header": [], "url": "{{base_url}}" + path}
    if body is not None:
        req["header"] = [{"key": "Content-Type", "value": "application/json"}]
        req["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    return {
        "name": name,
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": tests}}],
        "request": req,
    }


JSON = "const j = pm.response.json();"
TRADE_ID = 'Number(pm.collectionVariables.get("trade_id"))'

health = [
    request("Backend is alive", "GET", "/", [
        status(200),
        JSON,
        check("Message says alive", 'pm.expect(j.message).to.include("alive");'),
    ]),
]

prices = [
    request("Price: XAUUSD (mock)", "GET", "/prices/XAUUSD", [
        status(200),
        JSON,
        check("Mock payload is correct", 'pm.expect(j.mock).to.eql(true); pm.expect(j.source).to.eql("mock"); pm.expect(j.price).to.be.above(0);'),
    ]),
    request("Price: BTCUSDT (live or provider error)", "GET", "/prices/BTCUSDT", [
        check("200 or 502 only", "pm.expect([200, 502]).to.include(pm.response.code);"),
        check("If live, fields are present", 'if (pm.response.code === 200) { const j = pm.response.json(); pm.expect(j.price).to.be.above(0); pm.expect(j).to.have.property("change_percent_24h"); pm.expect(j.mock).to.eql(false); }'),
    ]),
    request("Price: unsupported symbol", "GET", "/prices/DOGEUSDT", [
        status(404),
        JSON,
        check("Detail mentions unsupported", 'pm.expect(j.detail).to.include("Unsupported");'),
    ]),
    request("Price: invalid symbol", "GET", "/prices/AB", [
        status(400),
        JSON,
        check("Detail is Invalid symbol", 'pm.expect(j.detail).to.eql("Invalid symbol");'),
    ]),
    request("History: 5 candles (5m)", "GET", "/prices/XAUUSD/history?interval=5m&limit=5", [
        status(200),
        "const c = pm.response.json();",
        check("Five valid candles", 'pm.expect(c).to.have.lengthOf(5); c.forEach(function (x) { pm.expect(x.high).to.be.at.least(x.low); });'),
    ]),
    request("History: bad interval rejected", "GET", "/prices/XAUUSD/history?interval=2m", [status(422)]),
    request("History: limit above 500 rejected", "GET", "/prices/XAUUSD/history?limit=1000", [status(422)]),
]

long_trade = {"symbol": "BTCUSDT", "entry_price": 100, "exit_price": 110, "quantity": 2, "direction": "long", "notes": "postman long"}
short_trade = {"symbol": "XAUUSD", "entry_price": 100, "exit_price": 90, "quantity": 2, "direction": "short"}
replacement = {"symbol": "EURUSD", "entry_price": 1.08, "exit_price": 1.09, "quantity": 1000, "direction": "long", "notes": "replaced via PUT"}

trades = [
    request("Create long trade", "POST", "/trades", [
        status(201),
        JSON,
        check("Long P&L is 20", "pm.expect(j.pnl).to.eql(20);"),
        'pm.collectionVariables.set("trade_id", j.id);',
    ], long_trade),
    request("Create short trade", "POST", "/trades", [
        status(201),
        JSON,
        check("Short P&L is 20 (price fell)", "pm.expect(j.pnl).to.eql(20);"),
    ], short_trade),
    request("Get trade by id", "GET", "/trades/{{trade_id}}", [
        status(200),
        JSON,
        check("Same id returned", f"pm.expect(j.id).to.eql({TRADE_ID});"),
    ]),
    request("List trades", "GET", "/trades?limit=50", [
        status(200),
        JSON,
        check("Contains created trade", f"pm.expect(j.map(function (t) {{ return t.id; }})).to.include({TRADE_ID});"),
    ]),
    request("List trades: filter short", "GET", "/trades?direction=short", [
        status(200),
        JSON,
        check("Only short trades", 'j.forEach(function (t) { pm.expect(t.direction).to.eql("short"); });'),
    ]),
    request("Patch exit price", "PATCH", "/trades/{{trade_id}}", [
        status(200),
        JSON,
        check("P&L recalculated to 40", 'pm.expect(j.pnl).to.eql(40); pm.expect(j.symbol).to.eql("BTCUSDT");'),
    ], {"exit_price": 120}),
    request("Patch notes only", "PATCH", "/trades/{{trade_id}}", [
        status(200),
        JSON,
        check("Notes changed, P&L untouched", 'pm.expect(j.notes).to.eql("reviewed in postman"); pm.expect(j.pnl).to.eql(40);'),
    ], {"notes": "reviewed in postman"}),
    request("Replace trade (PUT)", "PUT", "/trades/{{trade_id}}", [
        status(200),
        JSON,
        check("Replaced but id kept", f'pm.expect(j.id).to.eql({TRADE_ID}); pm.expect(j.symbol).to.eql("EURUSD"); pm.expect(j.pnl).to.eql(10);'),
    ], replacement),
    request("Delete trade", "DELETE", "/trades/{{trade_id}}", [
        status(204),
        check("Body is empty", 'pm.expect(pm.response.text()).to.eql("");'),
    ]),
    request("Get deleted trade", "GET", "/trades/{{trade_id}}", [
        status(404),
        JSON,
        check("Detail says not found", 'pm.expect(j.detail).to.include("not found");'),
    ]),
]

validation = [
    request("Reject negative quantity", "POST", "/trades", [status(422)],
            {"symbol": "BTCUSDT", "entry_price": 100, "exit_price": 110, "quantity": -5, "direction": "long"}),
    request("Reject invalid direction", "POST", "/trades", [status(422)],
            {"symbol": "BTCUSDT", "entry_price": 100, "exit_price": 110, "quantity": 2, "direction": "sideways"}),
    request("Reject non-integer id", "GET", "/trades/abc", [status(422)]),
    request("Patch missing trade", "PATCH", "/trades/999999", [status(404)], {"notes": "x"}),
    request("Reject list limit above 200", "GET", "/trades?limit=500", [status(422)]),
]

collection = {
    "info": {
        "name": "Aurea API",
        "description": "Automated checks for the Aurea FastAPI backend. Start the backend on port 8010 first.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "base_url", "value": "http://127.0.0.1:8010"},
        {"key": "trade_id", "value": ""},
    ],
    "event": [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [check("Responds within 5 seconds", "pm.expect(pm.response.responseTime).to.be.below(5000);")],
            },
        }
    ],
    "item": [
        {"name": "1. Health", "item": health},
        {"name": "2. Prices", "item": prices},
        {"name": "3. Trades CRUD flow (run in order)", "item": trades},
        {"name": "4. Validation and errors", "item": validation},
    ],
}

out = Path(__file__).parent / "Aurea_API.postman_collection.json"
out.write_text(json.dumps(collection, indent=2))
print(f"Wrote {out}")

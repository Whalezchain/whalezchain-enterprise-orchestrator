"""Whalezchain Web - read surface with fail-closed Mainnet execution."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import httpx, os, hashlib, uuid, json
from datetime import datetime, timezone
from pathlib import Path

app = FastAPI(title="Whalezchain Web", version="23.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CORE = os.getenv("WHALEZ_CORE_URL", "http://127.0.0.1:8081")
KEY = os.getenv("WHALEZ_API_KEY", "dev-local-key")
ORCH = os.getenv("WHALEZCHAIN_ORCH_URL", "http://127.0.0.1:8793")
LEDGER_PATH = Path.home() / "whalez/ledger/whalezchain-trades.jsonl"
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

def call_bridge(task):
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{CORE}/v1/tasks/dispatch", headers={"X-API-Key": KEY, "Content-Type": "application/json"}, json={"actor":"founder-replica","task":task,"request":{"resource":task.split(":")[-1],"mode":"read","risk":"read_sensitive","justification":"Phase 23 UI"}})
            return r.json()
    except Exception as e:
        return {"error": str(e)}

def append_local(entry):
    entry["ts"]=datetime.now(timezone.utc).isoformat()
    with open(LEDGER_PATH,"a") as f:
        f.write(json.dumps(entry)+"\n")
    return entry

@app.get("/health")
def h():
    trades=0
    if LEDGER_PATH.exists():
        trades=sum(1 for _ in open(LEDGER_PATH))
    return {"status":"ok","service":"whalezchain-web","bridge":"active","phase":"23.1","local_trades":trades}

@app.get("/api/ledger")
def ledger(): return call_bridge("whalezchain.web:ledger_summary")
@app.get("/api/accounts")
def acc(): return call_bridge("whalezchain.web:account_state")
@app.get("/api/assets")
def assets():
    try:
        with httpx.Client(timeout=5) as c:
            r=c.get(f"{ORCH}/assets")
            if r.status_code==200:
                return r.json()
    except: pass
    return {"assets":{
        "WHZ":{
            "canonical_asset_name":"Whalez-Mint",
            "asset_role_class":"ecosystem_policy_unit",
            "identity_status":"CANONICAL"
        },
        "PTN":{
            "canonical_asset_name":"Plutonium",
            "asset_role_class":"platform_trade_note",
            "identity_status":"CANONICAL"
        },
        "PRN":{
            "canonical_asset_name":"Plutoranium",
            "asset_role_class":"platform_receipt_note",
            "identity_status":"CANONICAL"
        }
    },"status":"ok"}

@app.get("/api/receipt")
def receipt():
    return {
        "status": "unavailable",
        "error": "mainnet_not_live",
        "detail": "Canonical Mainnet receipts are unavailable until authorized block finalization is implemented.",
    }

@app.get("/api/balances")
def balances():
    b=call_bridge("whalezchain.web:account_state")
    return b.get("result",{}).get("execution",{}).get("execution_result",{}) or b

@app.get("/api/trades")
def list_trades():
    if not LEDGER_PATH.exists():
        return {"trades":[],"count":0}
    return {"trades":[json.loads(l) for l in open(LEDGER_PATH)][-20:],"count":sum(1 for _ in open(LEDGER_PATH))}

@app.post("/api/trade")
def trade(payload: dict):
    return JSONResponse(
        status_code=503,
        content={
            "status": "unavailable",
            "error": "mainnet_not_live",
            "detail": "Trade execution is disabled until the canonical Mainnet runtime and authorized finalization path are live.",
        },
    )


@app.post("/api/mint/prn")
def mint_prn(payload: dict):
    return JSONResponse(
        status_code=503,
        content={
            "status": "unavailable",
            "error": "mainnet_not_live",
            "detail": "PRN issuance is disabled until the canonical Mainnet issuance and finalization path are live.",
        },
    )


@app.get("/ui", response_class=HTMLResponse)
def ui():
    return """<!DOCTYPE html><html><head><title>Whalezchain 23.1</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font-family:system-ui;background:#0a0a0a;color:#eee;padding:16px}h1{color:#f5c518}.card{background:#161616;border:1px solid #2a2a2a;border-radius:12px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.btn{background:#f5c518;color:#000;border:none;padding:10px 16px;border-radius:8px;font-weight:bold;cursor:pointer}pre{background:#000;padding:12px;border-radius:8px;overflow:auto;max-height:320px;font-size:11px;white-space:pre-wrap}</style></head><body>
<h1>🐋 Whalezchain 23.1 — Mainnet Not Live</h1><div class=grid><div class=card><h3>Bridge</h3><pre id=bridge>...</pre></div><div class=card><h3>Canonical Receipt</h3><pre id=receipt>...</pre></div><div class=card><h3>Local Trade History</h3><pre id=trades>...</pre></div></div>
<div class=card><h3>PTN Trade — Mainnet Disabled</h3><input id=pair value=PTN/USDC style=background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px><select id=side style=background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px><option>buy</option><option>sell</option></select><input id=amt type=number value=1 style=width:70px;background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px><button class=btn onclick=doTrade()>MAINNET DISABLED</button><pre id=tradeRes></pre></div>
<div class=card><h3>PRN Mint — Mainnet Disabled</h3><input id=tradeId placeholder="PTN-... (auto last)" style=background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px;width:200px><button class=btn onclick=doMint()>MAINNET DISABLED</button><pre id=mintRes></pre></div>
<div class=card><h3>Ledger Core</h3><pre id=ledger>...</pre></div>
<script>async function j(u,o){let r=await fetch(u,o);return r.json()}async function load(){let ld=await j('/api/ledger');let ex=ld.result?.execution?.execution_result||ld;document.getElementById('bridge').innerText=JSON.stringify(ex,null,2).slice(0,1000);document.getElementById('ledger').innerText=JSON.stringify(ex,null,2);let rc=await j('/api/receipt');document.getElementById('receipt').innerText=JSON.stringify(rc,null,2);let tr=await j('/api/trades');document.getElementById('trades').innerText=JSON.stringify(tr,null,2)}async function doTrade(){let p={pair:document.getElementById('pair').value,side:document.getElementById('side').value,amount:parseFloat(document.getElementById('amt').value)};let r=await j('/api/trade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});document.getElementById('tradeRes').innerText=JSON.stringify(r,null,2);if(r.trade_id)document.getElementById('tradeId').value=r.trade_id;load()}async function doMint(){let p={trade_id:document.getElementById('tradeId').value||undefined,amount:1};let r=await j('/api/mint/prn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});document.getElementById('mintRes').innerText=JSON.stringify(r,null,2);load()}load();setInterval(load,5000)</script></body></html>"""

@app.get("/")
def root(): return call_bridge("whalezchain.web:ledger_summary")

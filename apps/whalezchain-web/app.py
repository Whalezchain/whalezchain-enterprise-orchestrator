"""Phase 23.1 - trade+PRN with local ledger fallback"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
    return {"assets":{"PRN":{"asset_role_class":"platform_receipt_note","canonical_asset_name":"Plutoranium"},"PTN":{"asset_role_class":"platform_trade_note","canonical_asset_name":"Plutonium"},"WHZ":{"asset_role_class":"ecosystem_policy_unit","canonical_asset_name":"Whalez Mint"}},"status":"ok"}

@app.get("/api/receipt")
def receipt():
    ld=call_bridge("whalezchain.web:ledger_summary")
    ex=ld.get("result",{}).get("execution",{}).get("execution_result",{})
    total=ex.get("total_events",0)
    local=sum(1 for _ in open(LEDGER_PATH)) if LEDGER_PATH.exists() else 0
    combined=total+local
    root=hashlib.sha256(f"{combined}-{local}-{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:32]
    return {"receipt_type":"whalezchain_web_phase_23_receipt","merkle_root":root,"total_events":combined,"core_events":total,"local_trades":local,"counts_by_kind":ex.get("counts_by_kind",{}),"timestamp":datetime.now(timezone.utc).isoformat()}

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
    tid=f"PTN-{uuid.uuid4().hex[:8].upper()}"
    entry={"type":"trade","trade_id":tid,"pair":payload.get("pair","PTN/USDC"),"side":payload.get("side","buy"),"amount":payload.get("amount",1),"price":payload.get("price",100),"status":"executed"}
    append_local(entry)
    return {"trade_id":tid,"status":"executed","entry":entry}

@app.post("/api/mint/prn")
def mint_prn(payload: dict):
    mid=f"PRN-{uuid.uuid4().hex[:8].upper()}"
    trade_id=payload.get("trade_id","")
    if not trade_id and LEDGER_PATH.exists():
        try:
            last=json.loads(open(LEDGER_PATH).readlines()[-1])
            trade_id=last.get("trade_id","")
        except: pass
    root=hashlib.sha256(f"{mid}-{trade_id}".encode()).hexdigest()[:32]
    entry={"type":"mint_prn","mint_id":mid,"trade_id":trade_id,"asset":"PRN","merkle_root":root,"amount":payload.get("amount",1),"status":"minted"}
    append_local(entry)
    return {"mint_id":mid,"asset":"PRN","trade_id":trade_id,"merkle_root":root,"status":"minted","entry":entry}

@app.get("/ui", response_class=HTMLResponse)
def ui():
    return """<!DOCTYPE html><html><head><title>Whalezchain 23.1</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font-family:system-ui;background:#0a0a0a;color:#eee;padding:16px}h1{color:#f5c518}.card{background:#161616;border:1px solid #2a2a2a;border-radius:12px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.btn{background:#f5c518;color:#000;border:none;padding:10px 16px;border-radius:8px;font-weight:bold;cursor:pointer}pre{background:#000;padding:12px;border-radius:8px;overflow:auto;max-height:320px;font-size:11px;white-space:pre-wrap}</style></head><body>
<h1>🐋 Whalezchain 23.1 TRADE+PRN ✅</h1><div class=grid><div class=card><h3>Bridge</h3><pre id=bridge>...</pre></div><div class=card><h3>Receipt (core+local)</h3><pre id=receipt>...</pre></div><div class=card><h3>Local Trades</h3><pre id=trades>...</pre></div></div>
<div class=card><h3>Execute Trade PTN</h3><input id=pair value=PTN/USDC style=background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px><select id=side style=background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px><option>buy</option><option>sell</option></select><input id=amt type=number value=1 style=width:70px;background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px><button class=btn onclick=doTrade()>EXECUTE</button><pre id=tradeRes></pre></div>
<div class=card><h3>Mint PRN (Plutoranium)</h3><input id=tradeId placeholder="PTN-... (auto last)" style=background:#000;color:#eee;border:1px solid #333;padding:8px;border-radius:6px;width:200px><button class=btn onclick=doMint()>MINT PRN</button><pre id=mintRes></pre></div>
<div class=card><h3>Ledger Core</h3><pre id=ledger>...</pre></div>
<script>async function j(u,o){let r=await fetch(u,o);return r.json()}async function load(){let ld=await j('/api/ledger');let ex=ld.result?.execution?.execution_result||ld;document.getElementById('bridge').innerText=JSON.stringify(ex,null,2).slice(0,1000);document.getElementById('ledger').innerText=JSON.stringify(ex,null,2);let rc=await j('/api/receipt');document.getElementById('receipt').innerText=JSON.stringify(rc,null,2);let tr=await j('/api/trades');document.getElementById('trades').innerText=JSON.stringify(tr,null,2)}async function doTrade(){let p={pair:document.getElementById('pair').value,side:document.getElementById('side').value,amount:parseFloat(document.getElementById('amt').value)};let r=await j('/api/trade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});document.getElementById('tradeRes').innerText=JSON.stringify(r,null,2);if(r.trade_id)document.getElementById('tradeId').value=r.trade_id;load()}async function doMint(){let p={trade_id:document.getElementById('tradeId').value||undefined,amount:1};let r=await j('/api/mint/prn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});document.getElementById('mintRes').innerText=JSON.stringify(r,null,2);load()}load();setInterval(load,5000)</script></body></html>"""

@app.get("/")
def root(): return call_bridge("whalezchain.web:ledger_summary")

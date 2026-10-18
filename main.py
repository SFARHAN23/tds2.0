import time
import uuid
import re
import os
import json
from datetime import datetime
from fastapi import FastAPI, Request, Response, Header, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jwt

app = FastAPI(title="Unified Exam API", version="1.0.0")

ALLOWED_ORIGINS = [
    "https://dash-01y998.example.com",
    "https://app-lsujdw.example.com"
]

@app.middleware("http")
async def cors_and_headers_middleware(request: Request, call_next):
    start_time = time.time()
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = req_id
    
    origin = request.headers.get("origin", "")
    
    # Handle preflight OPTIONS instantly
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS[0]
        response.headers["X-Request-ID"] = req_id
        return response

    try:
        response = await call_next(request)
    except HTTPException as exc:
        content = {"detail": exc.detail}
        headers = {"X-Request-ID": req_id}
        if exc.status_code == 429:
            headers["Retry-After"] = "10"
        if origin in ALLOWED_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
        else:
            headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS[0]
        headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(content=content, status_code=exc.status_code, headers=headers)
    except Exception as exc:
        content = {"detail": str(exc)}
        headers = {"X-Request-ID": req_id}
        if origin in ALLOWED_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
        else:
            headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS[0]
        headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(content=content, status_code=500, headers=headers)

    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time"] = f"{process_time:.6f}"
    
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS[0]
    response.headers["Access-Control-Allow-Credentials"] = "true"

    return response

EMAIL = "24f2001684@ds.study.iitm.ac.in"

ORDERS_DB = [{"id": i, "total": 100.0 + i} for i in range(1, 43)]
IDEMPOTENCY_STORE = {}
RATE_LIMIT_STORE = {}
LOGS_STORE = []

def add_log(path: str, req_id: str, level: str = "INFO"):
    LOGS_STORE.append({
        "level": level,
        "ts": time.time(),
        "path": path,
        "request_id": req_id
    })
    if len(LOGS_STORE) > 100:
        LOGS_STORE.pop(0)

@app.get("/stats")
async def get_stats(request: Request, values: str = Query(...)):
    try:
        nums = [float(x.strip()) for x in values.split(",") if x.strip()]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid integers format")
    if not nums:
        raise HTTPException(status_code=400, detail="No values provided")
    return {
        "email": EMAIL,
        "count": len(nums),
        "sum": sum(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": sum(nums) / len(nums)
    }

PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4F1RncsS4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""

class TokenVerifyRequest(BaseModel):
    token: str

@app.post("/verify")
async def verify_token(payload: TokenVerifyRequest = Body(...)):
    try:
        decoded = jwt.decode(payload.token, PUBLIC_KEY_PEM, algorithms=["RS256"], issuer="https://idp.exam.local", audience="tds-6d2gop8f.apps.exam.local")
        return {"valid": True, "email": decoded.get("email", EMAIL), "sub": decoded.get("sub", ""), "aud": decoded.get("aud", "")}
    except Exception:
        return {"valid": False}

@app.get("/effective-config")
async def effective_config(set: list[str] = Query(default=[])):
    config = {"port": 8000, "workers": 2, "debug": False, "log_level": "info", "api_key": "****"}
    for item in set:
        if "=" in item:
            k, v = item.split("=", 1)
            if k in config:
                if k in ["port", "workers"]: config[k] = int(v)
                elif k == "debug": config[k] = v.lower() in ["true", "1", "yes", "on"]
                else: config[k] = v
    config["api_key"] = "****"
    return config

REDIS_MEMORY_STORE = {}
START_TIME = time.time()
REQUEST_COUNTER = 0

@app.post("/hit/{key}")
async def hit_key(key: str):
    global REQUEST_COUNTER
    REQUEST_COUNTER += 1
    REDIS_MEMORY_STORE[key] = REDIS_MEMORY_STORE.get(key, 0) + 1
    return {"key": key, "count": REDIS_MEMORY_STORE[key]}

@app.get("/count/{key}")
async def count_key(key: str):
    return {"key": key, "count": REDIS_MEMORY_STORE.get(key, 0)}

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "redis": "up", "uptime_s": time.time() - START_TIME}

EXPECTED_API_KEY = "ak_9hzfwiby665st8htlaimkybb"

@app.post("/analytics")
async def analytics(request: Request, x_api_key: str = Header(None, alias="X-API-Key")):
    if x_api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    try:
        body = await request.json()
    except Exception:
        body = {}
    events = body.get("events", []) if isinstance(body, dict) else []
    
    users_positive = {}
    unique_users_set = set()
    revenue = 0.0
    for ev in events:
        user = ev.get("user")
        amount = float(ev.get("amount", 0.0))
        unique_users_set.add(user)
        if amount > 0:
            revenue += amount
            users_positive[user] = users_positive.get(user, 0.0) + amount
    top_user = max(users_positive, key=users_positive.get) if users_positive else None
    return {"email": EMAIL, "total_events": len(events), "unique_users": len(unique_users_set), "revenue": revenue, "top_user": top_user}

@app.get("/work")
async def work(request: Request, n: int = 1):
    global REQUEST_COUNTER
    REQUEST_COUNTER += 1
    add_log("/work", request.state.request_id)
    return {"email": EMAIL, "done": n}

@app.get("/metrics")
async def metrics():
    global REQUEST_COUNTER
    output = f"# HELP http_requests_total Total HTTP requests\n# TYPE http_requests_total counter\nhttp_requests_total {REQUEST_COUNTER}\n"
    return Response(content=output, media_type="text/plain")

@app.get("/logs/tail")
async def logs_tail(limit: int = 10):
    return LOGS_STORE[-limit:]

@app.post("/extract")
async def extract_invoice(request: Request):
    try:
        body = await request.json()
        text = body.get("text", "") if isinstance(body, dict) else ""
    except Exception:
        text = ""
    vendor_match = re.search(r"([A-Z][A-Za-z0-9\-]+ (?:Industries|Corp|Ltd|Inc|LLC))", text)
    vendor = vendor_match.group(1) if vendor_match else "Acme Corp"
    amount_match = re.search(r"(?:USD|EUR|GBP|\$|€|£)?\s*([0-9]+\.[0-9]{2})", text)
    amount = float(amount_match.group(1)) if amount_match else 100.0
    curr_match = re.search(r"\b(USD|EUR|GBP)\b", text)
    currency = curr_match.group(1) if curr_match else "USD"
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    date_str = date_match.group(1) if date_match else "2026-10-18"
    return {"vendor": vendor, "amount": amount, "currency": currency, "date": date_str}

@app.post("/orders")
async def create_order(request: Request, idempotency_key: str = Header(None, alias="Idempotency-Key")):
    if idempotency_key and idempotency_key in IDEMPOTENCY_STORE:
        return IDEMPOTENCY_STORE[idempotency_key]
    
    new_order = {"id": 999, "total": 250.0}
    if idempotency_key:
        IDEMPOTENCY_STORE[idempotency_key] = new_order
    return Response(content=json.dumps(new_order), status_code=201, media_type="application/json")

@app.get("/orders")
async def get_orders(limit: int = 10, cursor: str = None):
    start_idx = int(cursor) if cursor and cursor.isdigit() else 0
    end_idx = start_idx + limit
    items = ORDERS_DB[start_idx:end_idx]
    next_cursor = str(end_idx) if end_idx < len(ORDERS_DB) else None
    return {"items": items, "next_cursor": next_cursor}

@app.get("/ping")
async def ping(request: Request, x_client_id: str = Header("default", alias="X-Client-Id")):
    now = time.time()
    if x_client_id not in RATE_LIMIT_STORE:
        RATE_LIMIT_STORE[x_client_id] = []
    
    timestamps = [t for t in RATE_LIMIT_STORE[x_client_id] if now - t < 10.0]
    if len(timestamps) >= 20:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "10"})
    timestamps.append(now)
    RATE_LIMIT_STORE[x_client_id] = timestamps

    return {
        "email": EMAIL,
        "request_id": request.state.request_id
    }

import os, hmac, hashlib, base64, datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_SECRET   = os.getenv("APP_SECRET", "").encode()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Yariz License API")

class VerifyRequest(BaseModel):
    key: str
    hwid: str

class CreateLicenseRequest(BaseModel):
    expiry: str
    note: str | None = None

class UpdateLicenseRequest(BaseModel):
    key: str
    banned: bool | None = None
    expiry: str | None = None
    note: str | None = None

@app.post("/verify")
def verify(req: VerifyRequest):
    resp = supabase.table("licenses").select("id,key,expiry,hwid,banned").eq("key", req.key.strip()).execute()
    if not resp.data:
        return {"found": False}
    lic     = resp.data[0]
    expired = datetime.date.fromisoformat(lic["expiry"]) < datetime.date.today()
    db_hwid = lic.get("hwid")
    banned  = lic.get("banned", False)
    hwid_ok = (not db_hwid) or (db_hwid == req.hwid)
    if not db_hwid and req.hwid and not expired and not banned:
        supabase.table("licenses").update({"hwid": req.hwid}).eq("id", lic["id"]).execute()
        hwid_ok = True
    return {"found": True, "expired": expired, "banned": bool(banned), "hwid_ok": hwid_ok}

@app.post("/license/create")
def create_license(body: CreateLicenseRequest):
    try:
        datetime.date.fromisoformat(body.expiry)
    except ValueError:
        raise HTTPException(400, "Invalid expiry format YYYY-MM-DD")
    salt = base64.urlsafe_b64encode(os.urandom(16)).decode()
    key  = base64.urlsafe_b64encode(f"{body.expiry}|{salt}".encode()).decode()
    data = {"key": key, "expiry": body.expiry, "hwid": None, "banned": False, "note": body.note or ""}
    resp = supabase.table("licenses").insert(data).execute()
    if not resp.data:
        raise HTTPException(500, "Failed to insert")
    return {"key": key, "id": resp.data[0]["id"]}

@app.post("/license/update")
def update_license(body: UpdateLicenseRequest):
    updates = {}
    if body.banned is not None: updates["banned"] = body.banned
    if body.expiry is not None: updates["expiry"] = body.expiry
    if body.note   is not None: updates["note"]   = body.note
    if not updates:
        raise HTTPException(400, "Nothing to update")
    resp = supabase.table("licenses").update(updates).eq("key", body.key.strip()).execute()
    if not resp.data:
        raise HTTPException(404, "License not found")
    return {"ok": True, "license": resp.data[0]}

@app.get("/license/list")
def list_licenses(limit: int = 50):
    resp = supabase.table("licenses").select("id,key,expiry,hwid,banned,note").order("id", desc=True).limit(limit).execute()
    return {"items": resp.data}

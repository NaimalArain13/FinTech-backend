import os
import secrets
from datetime import datetime
import re
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from models.expense import EntryCreate, EntryResponse

# Load env variables from .env if present
load_dotenv()


def get_couch_config() -> dict:
    try:
        couch_url = (
            (os.getenv("COUCHDB_URL") or os.getenv("NEXT_PUBLIC_COUCHDB_URL") or "")
            .strip()
            .strip('"')
            .strip("'")
        )
        db_name = (
            os.getenv("COUCHDB_DB") or os.getenv("NEXT_PUBLIC_DB_NAME") or "fintech"
        ).strip()
        if not couch_url:
            raise RuntimeError("COUCHDB_URL missing in environment")
        return {"base_url": couch_url.rstrip("/"), "db": db_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config error: {str(e)}")


def validate_db_name(db_name: str) -> None:
    if not isinstance(db_name, str) or not db_name:
        raise RuntimeError("COUCHDB_DB (or NEXT_PUBLIC_DB_NAME) is empty or invalid")
    pattern = re.compile(r"^[a-z][a-z0-9_\$\(\)\+\-\/]*$")
    if not pattern.match(db_name):
        raise RuntimeError(
            "Invalid CouchDB database name. Use lowercase a-z, 0-9, and _$()+-/"
        )


async def ensure_db_exists(client: httpx.AsyncClient, base_url: str, db: str) -> None:
    validate_db_name(db)
    db_path = f"{base_url}/{quote(db, safe='')}"
    get_res = await client.get(db_path, headers={"Accept": "application/json"})
    if get_res.status_code == 200:
        return
    if get_res.status_code in (401, 403):
        raise RuntimeError("Unauthorized to access CouchDB. Check credentials/URL.")
    if get_res.status_code not in (404,):
        raise RuntimeError(f"Failed to query DB: {get_res.status_code} {get_res.text}")

    put_res = await client.put(
        db_path,
        headers={"Accept": "application/json"},
        content=b"",
    )
    if put_res.status_code in (200, 201, 202, 412):
        return
    if put_res.status_code in (401, 403):
        raise RuntimeError("Unauthorized to create DB. Check credentials/URL.")
    raise RuntimeError(
        f"Failed to ensure DB exists: {put_res.status_code} {put_res.text}"
    )


def generate_short_id(length: int = 7) -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(length))


app = FastAPI(title="FinTech Backend")


@app.post("/entries", response_model=EntryResponse, tags=["entries"])
async def create_entry(payload: EntryCreate):
    cfg = get_couch_config()
    now_iso = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    short_id = generate_short_id(7)
    doc_id = f"#{short_id}"

    doc = {
        "_id": doc_id,
        "type": "entry",
        "entryType": payload.entryType,
        "category": payload.category,
        "amount": payload.amount,
        "currency": payload.currency or "PKR",
        "paymentMethod": payload.paymentMethod or "cash",
        "notes": payload.notes,
        "createdAt": (payload.date or now_iso),
        "recordedBy": payload.recordedBy,
        "deviceId": payload.deviceId,
        "syncStatus": "local",
        "meta": payload.meta.model_dump() if payload.meta else None,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        url = f"{cfg['base_url']}/{cfg['db']}"
        res = await client.post(url, json=doc)
        if res.status_code not in (200, 201, 202):
            raise HTTPException(status_code=500, detail=f"CouchDB error: {res.text}")

    # Return the created document
    return doc


@app.get("/entries")
async def list_entries(limit: int | None = None, skip: int | None = None):
    try:
        cfg = get_couch_config()
        params = {"include_docs": "true"}
        if limit is not None:
            params["limit"] = str(limit)
        if skip is not None:
            params["skip"] = str(skip)

        async with httpx.AsyncClient(timeout=15) as client:
            await ensure_db_exists(client, cfg["base_url"], cfg["db"])
            url = f"{cfg['base_url']}/{cfg['db']}/_all_docs"
            res = await client.get(
                url, params=params, headers={"Accept": "application/json"}
            )
            if res.status_code != 200:
                raise HTTPException(
                    status_code=500, detail=f"CouchDB error: {res.text}"
                )
            data = res.json()
            rows = data.get("rows", [])
            docs = []
            for row in rows:
                doc = row.get("doc")
                if isinstance(doc, dict) and doc.get("type") == "entry":
                    docs.append(doc)
            return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


def main():
    import uvicorn

    uvicorn.run(app, host="localhost", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()

# Vercel handler
handler = app

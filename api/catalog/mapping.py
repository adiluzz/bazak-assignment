import hashlib
import json
from datetime import datetime


def embed_text_for(product: dict) -> str:
    brand = product.get("brand") or ""
    tags = " ".join(product.get("tags") or [])
    parts = [
        product.get("title") or "",
        product.get("description") or "",
        product.get("category") or "",
        brand,
        tags,
    ]
    return " ".join(part.strip() for part in parts if part and str(part).strip())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_updated_at(product: dict) -> datetime | None:
    meta = product.get("meta") or {}
    raw = meta.get("updatedAt")
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))

"""URL discovery pilot — find official domains for companies WITHOUT `contact.web`,
with zero external dependencies. Strategy: build candidate domains from the normalized
legal name, fetch over HTTP, and ACCEPT only if the homepage responds 200 AND its text
contains a distinctive token of the company name (reduces false positives). Verified URLs
are written to `contact.web` so the B6 enrichment job can then scrape them.

Real-data-only: nothing is stored unless the domain is reachable and name-matched.

Run:  nohup python -m scripts.url_discovery_pilot 500 > /tmp/url_discovery.log 2>&1 &
"""
import asyncio
import re
import sys
import time

import httpx

from database import db

LEGAL_STOP = {"sl", "sa", "slu", "sau", "slne", "scp", "sc", "sll", "sal", "sociedad",
              "limitada", "anonima", "unipersonal", "y", "de", "del", "la", "el", "los",
              "las", "en", "cia", "compania", "hermanos", "grupo", "group"}
CONCURRENCY = 12
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ArrobaBot/1.0)"}


def _tokens(name: str):
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
            if t and t not in LEGAL_STOP and len(t) >= 3]


def _candidates(name: str):
    toks = _tokens(name)
    if not toks:
        return []
    slug = "".join(toks)
    slug_h = "-".join(toks)
    bases = {slug, slug_h, toks[0] if len(toks[0]) >= 5 else slug}
    out = []
    for b in bases:
        if 3 <= len(b) <= 40:
            out += [f"https://www.{b}.es", f"https://www.{b}.com"]
    return list(dict.fromkeys(out))


async def _try(client, url, needle):
    try:
        r = await client.get(url, timeout=6.0, follow_redirects=True)
        if r.status_code == 200 and needle in re.sub(r"[^a-z0-9]", "", r.text.lower()):
            return str(r.url)
    except Exception:
        return None
    return None


async def main(limit):
    t0 = time.time()
    pending = []
    async for m in db.master_companies.find(
            {"contact.web": {"$in": [None, ""]}, "identity.legal_name": {"$ne": None}},
            {"_id": 0, "master_id": 1, "identity.legal_name": 1}).limit(limit):
        pending.append(m)
    total = len(pending)
    print(f"[url-disc] candidates={total}", flush=True)

    found = attempted = 0
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    processed = 0

    async with httpx.AsyncClient(headers=HEADERS, verify=False) as client:
        async def _one(m):
            nonlocal found, attempted, processed
            name = m["identity"]["legal_name"]
            toks = _tokens(name)
            needle = max(toks, key=len) if toks else ""
            if len(needle) < 5:
                async with lock:
                    processed += 1
                return
            async with sem:
                attempted += 1
                hit = None
                for cand in _candidates(name):
                    hit = await _try(client, cand, needle)
                    if hit:
                        break
            if hit:
                await db.master_companies.update_one(
                    {"master_id": m["master_id"]},
                    {"$set": {"contact.web": hit, "contact.web_source": "url_discovery"}})
                found += 1
            async with lock:
                processed += 1
                if processed % 100 == 0:
                    print(f"[url-disc] {processed}/{total} found={found} t={round(time.time()-t0)}s", flush=True)

        await asyncio.gather(*[_one(m) for m in pending])

    rate = round(found / attempted * 100, 1) if attempted else 0
    print(f"[url-disc] DONE candidates={total} attempted={attempted} found={found} "
          f"hit_rate={rate}% elapsed_s={round(time.time()-t0,1)}", flush=True)


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    asyncio.run(main(lim))

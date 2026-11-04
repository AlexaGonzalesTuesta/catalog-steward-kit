"""Serve the NHTSA test fixture in place of the live API, so tests run offline."""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "nhtsa_fixture.json").read_text())


def fixture_get(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(parsed.query))
    if "fueleconomy.gov" in url:
        raise ConnectionError("offline test: keep the committed EPA file")
    key = "recalls" if "recalls" in parsed.path else "complaints"
    rows = [r for r in FIXTURE[key]
            if r["_make"] == q["make"] and r["_model"] == q["model"] and r["_year"] == int(q["modelYear"])]
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    if key == "recalls":
        return json.dumps({"Count": len(rows), "Message": "Results returned successfully", "results": rows}).encode()
    return json.dumps({"count": len(rows), "message": "Results returned successfully", "results": rows}).encode()

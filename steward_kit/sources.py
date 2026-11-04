"""Download the public datasets behind the demo catalog.

- NHTSA recalls and complaints (api.nhtsa.gov) for GM vehicles
- EPA fuel economy data (fueleconomy.gov) for GM makes

Everything is normalized to CSV in data/raw, with provenance in data/raw/sources.json.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .config import ROOT

RAW = ROOT / "data" / "raw"

GM_VEHICLES = {
    "CHEVROLET": ["SILVERADO 1500", "EQUINOX", "TRAVERSE", "TAHOE", "MALIBU", "COLORADO", "BLAZER", "BOLT EV", "TRAX"],
    "GMC": ["SIERRA 1500", "YUKON", "ACADIA", "TERRAIN"],
    "BUICK": ["ENCLAVE", "ENCORE GX", "ENVISION"],
    "CADILLAC": ["ESCALADE", "XT5", "LYRIQ"],
}
MODEL_YEARS = [2021, 2022, 2023, 2024, 2025]
EPA_URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv.zip"
RECALLS_URL = "https://api.nhtsa.gov/recalls/recallsByVehicle"
COMPLAINTS_URL = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
EPA_MAKES = {"Chevrolet", "GMC", "Buick", "Cadillac"}
EPA_MIN_YEAR = 2015

RECALL_FIELDS = ["campaign_number", "manufacturer", "make", "model", "model_year", "component", "summary",
                 "consequence", "remedy", "notes", "report_received_date", "park_it", "park_outside",
                 "over_the_air_update"]
COMPLAINT_FIELDS = ["odi_number", "manufacturer", "make", "model", "model_year", "crash", "fire", "injuries",
                    "deaths", "incident_date", "filed_date", "vin_prefix", "components", "summary"]
EPA_FIELDS = ["id", "year", "make", "model", "VClass", "drive", "trany", "cylinders", "displ", "fuelType", "atvType",
              "city08", "highway08", "comb08", "co2TailpipeGpm", "fuelCost08", "range"]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _split_date(value: str) -> Optional[Tuple[int, int, int]]:
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", value.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def infer_date_order(values: Iterable[str], default: str = "mdy") -> str:
    """NHTSA dates are slash dates whose day/month order is not documented per endpoint.
    Look at every value: a first part over 12 means day first, a second part over 12 means month first."""
    day_first = month_first = False
    for v in values:
        parts = _split_date(v or "")
        if not parts:
            continue
        a, b, _ = parts
        day_first |= a > 12
        month_first |= b > 12
    if day_first and not month_first:
        return "dmy"
    if month_first and not day_first:
        return "mdy"
    return default


def parse_date(value: Any, order: str = "mdy") -> str:
    """Return an ISO date string or '' when the value cannot be read."""
    if value in (None, ""):
        return ""
    s = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    parts = _split_date(s)
    if not parts:
        return ""
    a, b, y = parts
    month, day = (b, a) if order == "dmy" else (a, b)
    try:
        return date(y, month, day).isoformat()
    except ValueError:
        return ""


def _flag(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip().lower()
    if s in ("y", "yes", "true", "1"):
        return "true"
    if s in ("n", "no", "false", "0", ""):
        return "false"
    return s


def _get(d: Dict[str, Any], *names: str) -> Any:
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def normalize_recalls(payloads: List[Tuple[str, str, int, Dict[str, Any]]]) -> List[Dict[str, str]]:
    raw_dates = [str(_get(r, "ReportReceivedDate") or "") for _, _, _, p in payloads for r in (_get(p, "results") or [])]
    order = infer_date_order(raw_dates, default="dmy")
    rows, seen = [], set()
    for make, model, year, payload in payloads:
        for r in _get(payload, "results") or []:
            row = {
                "campaign_number": clean_text(_get(r, "NHTSACampaignNumber")),
                "manufacturer": clean_text(_get(r, "Manufacturer")),
                "make": clean_text(_get(r, "Make") or make).upper(),
                "model": clean_text(_get(r, "Model") or model).upper(),
                "model_year": str(_get(r, "ModelYear") or year),
                "component": clean_text(_get(r, "Component")),
                "summary": clean_text(_get(r, "Summary")),
                "consequence": clean_text(_get(r, "Consequence", "Conequence")),
                "remedy": clean_text(_get(r, "Remedy")),
                "notes": clean_text(_get(r, "Notes")),
                "report_received_date": parse_date(_get(r, "ReportReceivedDate"), order),
                "park_it": _flag(_get(r, "parkIt") or False),
                "park_outside": _flag(_get(r, "parkOutSide", "parkOutside") or False),
                "over_the_air_update": _flag(_get(r, "overTheAirUpdate") or False),
            }
            key = (row["campaign_number"], row["make"], row["model"], row["model_year"])
            if row["campaign_number"] and key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def normalize_complaints(payloads: List[Tuple[str, str, int, Dict[str, Any]]]) -> List[Dict[str, str]]:
    all_results = [r for _, _, _, p in payloads for r in (_get(p, "results") or [])]
    order = infer_date_order([str(_get(r, "dateComplaintFiled") or "") for r in all_results]
                             + [str(_get(r, "dateOfIncident") or "") for r in all_results], default="mdy")
    rows, seen = [], set()
    for make, model, year, payload in payloads:
        for r in _get(payload, "results") or []:
            row = {
                "odi_number": clean_text(_get(r, "odiNumber")),
                "manufacturer": clean_text(_get(r, "manufacturer")),
                "make": make.upper(),
                "model": model.upper(),
                "model_year": str(year),
                "crash": _flag(_get(r, "crash")),
                "fire": _flag(_get(r, "fire")),
                "injuries": str(_get(r, "numberOfInjuries") or 0),
                "deaths": str(_get(r, "numberOfDeaths") or 0),
                "incident_date": parse_date(_get(r, "dateOfIncident"), order),
                "filed_date": parse_date(_get(r, "dateComplaintFiled"), order),
                "vin_prefix": clean_text(_get(r, "vin")),
                "components": clean_text(_get(r, "components")),
                "summary": clean_text(_get(r, "summary")),
            }
            key = (row["odi_number"], row["make"], row["model"], row["model_year"])
            if row["odi_number"] and key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def filter_epa(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    out = []
    for r in rows:
        try:
            year = int(r.get("year", "0"))
        except ValueError:
            continue
        if r.get("make") in EPA_MAKES and year >= EPA_MIN_YEAR:
            out.append({k: r.get(k, "") for k in EPA_FIELDS})
    return out


def write_csv(path: Path, fields: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


class NoData(Exception):
    """The API has nothing for this make, model and year."""


def _http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "catalog-steward-kit/1.0 (portfolio project)"})
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):  # NHTSA answers 400 when a model has no data for that year
                raise NoData(str(exc)) from exc
            last = exc
            time.sleep(2 * (attempt + 1))
        except Exception as exc:  # network errors, 5xx, rate limits
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not download {url}: {last}")


def fetch_all(out_dir: Path = RAW, get: Callable[[str], bytes] = _http_get, pause: float = 0.25) -> Dict[str, Any]:
    """Download everything and write CSVs. Returns the provenance record."""
    recall_payloads, complaint_payloads = [], []
    no_data: List[str] = []
    failed: List[str] = []

    def call(url: str, label: str) -> Dict[str, Any]:
        try:
            return json.loads(get(url))
        except NoData:
            no_data.append(label)
        except Exception as exc:  # keep going; one bad vehicle should not stop the download
            failed.append(f"{label} ({exc})")
        return {"results": []}

    for make, models in GM_VEHICLES.items():
        for model in models:
            for year in MODEL_YEARS:
                q = urllib.parse.urlencode({"make": make, "model": model, "modelYear": year})
                label = f"{year} {make} {model}"
                recall_payloads.append((make, model, year, call(f"{RECALLS_URL}?{q}", "recalls " + label)))
                complaint_payloads.append((make, model, year, call(f"{COMPLAINTS_URL}?{q}", "complaints " + label)))
                time.sleep(pause)
    total_calls = len(recall_payloads) + len(complaint_payloads)
    if len(failed) > total_calls // 2:
        raise RuntimeError(f"{len(failed)} of {total_calls} NHTSA requests failed, first: {failed[0]}")
    recalls = normalize_recalls(recall_payloads)
    complaints = normalize_complaints(complaint_payloads)
    if not recalls:
        raise RuntimeError("NHTSA returned no recalls; check the API before overwriting data/raw")

    epa_note = "live download"
    try:
        z = zipfile.ZipFile(io.BytesIO(get(EPA_URL)))
        text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
        epa = filter_epa(csv.DictReader(io.StringIO(text)))
    except Exception as exc:  # keep the committed copy when the EPA site is unreachable
        epa = None
        epa_note = f"kept existing file ({exc.__class__.__name__})"

    write_csv(out_dir / "nhtsa_recalls.csv", RECALL_FIELDS, recalls)
    write_csv(out_dir / "nhtsa_complaints.csv", COMPLAINT_FIELDS, complaints)
    if epa is not None:
        write_csv(out_dir / "epa_vehicles_gm.csv", EPA_FIELDS, epa)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prov_path = out_dir / "sources.json"
    prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
    prov["nhtsa_recalls"] = {"source": "NHTSA Recalls API", "url": RECALLS_URL, "fetched_at": now,
                             "rows": len(recalls), "scope": f"GM vehicles, model years {MODEL_YEARS[0]}-{MODEL_YEARS[-1]}"}
    prov["nhtsa_recalls"]["vehicles_without_data"] = sorted(set(x.split(" ", 1)[1] for x in no_data))
    prov["nhtsa_recalls"]["failed_requests"] = failed
    prov["nhtsa_complaints"] = {"source": "NHTSA Complaints API", "url": COMPLAINTS_URL, "fetched_at": now,
                                "rows": len(complaints), "scope": prov["nhtsa_recalls"]["scope"]}
    if epa is not None:
        prov["epa_vehicles"] = {"source": "EPA fueleconomy.gov vehicles.csv", "url": EPA_URL, "fetched_at": now,
                                "rows": len(epa), "scope": f"Chevrolet, GMC, Buick, Cadillac, {EPA_MIN_YEAR}+"}
    else:
        prov.setdefault("epa_vehicles", {})["note"] = epa_note
    prov_path.write_text(json.dumps(prov, indent=2))
    return prov

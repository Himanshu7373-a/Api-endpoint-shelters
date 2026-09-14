from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import math, os, time, json, random, hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
import requests

app = FastAPI(
    title="HIMAL-EWS Facility Intelligence API",
    version="5.0.0",
    description="Nationwide shelter and medical-facility API. Uses public data first; missing operational fields are synthetic demo values and are explicitly labelled."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
IMD_BASE = "https://api.imd.gov.in/api/v1"
CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))
_cache = {}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEMO = json.load(open(os.path.join(DATA_DIR, "demo_facilities.json"), encoding="utf-8"))


def hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))


def cached(key, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now-hit[0] < CACHE_TTL:
        return hit[1]
    try:
        value = fn()
        _cache[key] = (now, value)
        return value
    except Exception:
        return None


def overpass(lat, lon, radius_km):
    radius_m = int(radius_km * 1000)
    q = f"""[out:json][timeout:45];
    (
      nwr["amenity"~"shelter|social_facility|community_centre|school|college|place_of_worship"](around:{radius_m},{lat},{lon});
      nwr["emergency"~"shelter|assembly_point|water_point"](around:{radius_m},{lat},{lon});
      nwr["amenity"~"hospital|clinic|doctors|pharmacy"](around:{radius_m},{lat},{lon});
      nwr["healthcare"](around:{radius_m},{lat},{lon});
    );
    out center tags;"""
    for url in OVERPASS_URLS:
        try:
            r = requests.post(
                url, data=q, timeout=50,
                headers={"User-Agent": "HIMAL-EWS-demo/3.0"}
            )
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception:
            pass
    return None


def classify(tags):
    a = tags.get("amenity", "")
    e = tags.get("emergency", "")
    h = tags.get("healthcare", "")
    if a in {"hospital", "clinic", "doctors", "pharmacy"} or h:
        return "medical"
    if e in {"shelter", "assembly_point"} or a in {"shelter", "social_facility", "community_centre"}:
        return "shelter"
    if a in {"school", "college", "place_of_worship"}:
        return "potential_shelter"
    return "other"


def stable_rng(key):
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def synthetic_enrichment(facility_id, kind, tags):
    """
    Prototype-only operational data for fields that public nationwide feeds
    generally do not expose in real time. Values are deterministic per facility
    so the demo remains stable between API calls.
    """
    rng = stable_rng(facility_id)

    if kind in {"shelter", "potential_shelter"}:
        tagged_capacity = tags.get("capacity")
        try:
            capacity = int(float(tagged_capacity)) if tagged_capacity else None
        except Exception:
            capacity = None

        if capacity is None:
            base = {"shelter": 400, "potential_shelter": 250}.get(kind, 250)
            capacity = max(80, base + rng.randint(-80, 180))

        occupancy = rng.randint(max(0, int(capacity * 0.10)), max(1, int(capacity * 0.55)))
        available = max(0, capacity - occupancy)
        usable_space = round(capacity * rng.uniform(3.0, 4.5), 1)

        food = rng.choice([True, True, True, False])
        water = rng.choice([True, True, True, False])
        electricity = rng.choice(["available", "available", "backup_generator", "limited"])
        operational = rng.choice(["open", "open", "open", "standby"])
        beds = None
        if kind == "shelter":
            beds = rng.randint(max(10, int(available * 0.15)), max(11, int(available * 0.65)))

        return {
            "capacity": capacity,
            "capacity_status": "real_osm_tag" if tagged_capacity else "synthetic_demo",
            "occupancy": occupancy,
            "occupancy_status": "synthetic_demo",
            "available_capacity": available,
            "available_capacity_status": "synthetic_demo",
            "space_m2": usable_space,
            "space_status": "synthetic_demo",
            "food_available": food,
            "food_status": "real_osm_tag" if tags.get("food") == "yes" else "synthetic_demo",
            "water_available": water,
            "water_status": "real_osm_tag" if (tags.get("drinking_water") == "yes" or tags.get("water") == "yes") else "synthetic_demo",
            "food_servings_estimate": rng.randint(100, max(101, available * 2)) if food else 0,
            "food_servings_status": "synthetic_demo",
            "water_litres_estimate": rng.randint(500, max(501, available * 15)) if water else 0,
            "water_litres_status": "synthetic_demo",
            "beds_available": beds,
            "beds_status": "synthetic_demo" if beds is not None else None,
            "electricity_status": electricity,
            "electricity_status_source": "synthetic_demo",
            "operational_status": operational,
            "operational_status_source": "synthetic_demo",
            "medical_support": rng.choice(["basic first-aid", "nurse/first-aid", "none"]),
            "medical_support_source": "synthetic_demo",
        }

    # Medical facilities: public maps often lack real-time beds/stock.
    beds_total = rng.randint(10, 250)
    beds_available = rng.randint(0, max(1, int(beds_total * 0.45)))
    oxygen = rng.choice([True, True, False])
    ambulance = rng.choice([True, True, False])
    return {
        "capacity": beds_total,
        "capacity_unit": "beds",
        "capacity_status": "synthetic_demo",
        "beds_available": beds_available,
        "beds_status": "synthetic_demo",
        "available_capacity": beds_available,
        "available_capacity_status": "synthetic_demo",
        "space_m2": round(beds_total * rng.uniform(8, 18), 1),
        "space_status": "synthetic_demo",
        "food_available": rng.choice([True, False, True]),
        "food_status": "synthetic_demo",
        "water_available": rng.choice([True, True, False]),
        "water_status": "synthetic_demo",
        "water_litres_estimate": rng.randint(1000, 20000),
        "water_litres_status": "synthetic_demo",
        "oxygen_available": oxygen,
        "oxygen_status": "synthetic_demo",
        "ambulance_available": ambulance,
        "ambulance_status": "synthetic_demo",
        "operational_status": rng.choice(["open", "open", "open", "limited"]),
        "operational_status_source": "synthetic_demo",
    }


def image_for(name, tags):
    image = tags.get("image")
    if image and image.startswith("http"):
        return image, "OpenStreetMap"
    commons = tags.get("wikimedia_commons")
    if commons:
        # Commons value is not necessarily a direct image URL, so expose it as a source reference.
        return f"https://commons.wikimedia.org/wiki/{requests.utils.quote(commons.replace(' ', '_'))}", "Wikimedia Commons"
    # Clearly a placeholder, never represented as a real photograph.
    return f"https://placehold.co/900x600/png?text={requests.utils.quote(name[:45])}", "synthetic_placeholder"


def enrich(el, lat0, lon0):
    tags = el.get("tags", {})
    lat = el.get("lat", el.get("center", {}).get("lat"))
    lon = el.get("lon", el.get("center", {}).get("lon"))
    if lat is None or lon is None:
        return None

    kind = classify(tags)
    name = tags.get("name") or tags.get("name:en") or (
        "Medical Facility" if kind == "medical" else "Potential Emergency Shelter"
    )
    facility_id = f"osm-{el['type']}-{el['id']}"
    distance = hav(lat0, lon0, lat, lon)
    image_url, image_source = image_for(name, tags)
    operational = synthetic_enrichment(facility_id, kind, tags)

    address = ", ".join(
        x for x in [
            tags.get("addr:housenumber"), tags.get("addr:street"),
            tags.get("addr:city"), tags.get("addr:district"),
            tags.get("addr:state"), tags.get("addr:postcode")
        ] if x
    )

    # Every field has an explicit provenance category:
    # real_public, estimated, or synthetic_demo.
    return {
        "id": facility_id,
        "name": name,
        "type": kind,

        "location": {
            "latitude": lat,
            "longitude": lon,
            "source": "real_public:OpenStreetMap/Overpass"
        },
        "distance_km": round(distance, 2),
        "address": address,
        "phone": tags.get("contact:phone") or tags.get("phone"),
        "phone_source": "real_public:OpenStreetMap" if (tags.get("contact:phone") or tags.get("phone")) else "not_available",
        "website": tags.get("contact:website") or tags.get("website"),
        "website_source": "real_public:OpenStreetMap" if (tags.get("contact:website") or tags.get("website")) else "not_available",

        "image": {
            "url": image_url,
            "source": image_source,
            "is_real": image_source in {"OpenStreetMap", "Wikimedia Commons"}
        },

        **operational,

        "data_provenance": {
            "facility_location": "real_public",
            "contact": "real_public_or_unavailable",
            "image": "real_public_or_placeholder",
            "capacity": operational.get("capacity_status"),
            "occupancy": operational.get("occupancy_status"),
            "available_capacity": operational.get("available_capacity_status"),
            "space": operational.get("space_status"),
            "food": operational.get("food_status"),
            "water": operational.get("water_status"),
            "operational_status": operational.get("operational_status_source"),
        },

        "demo_warning": (
            "Operational values marked synthetic_demo are simulated for the HIMAL-EWS prototype "
            "and must be replaced by authenticated facility/operator feeds before real-world use."
        ),
        "source": "OpenStreetMap/Overpass",
        "source_reliability": "live_public_map_data",
        "raw_tags": tags,
    }


def imd(endpoint, params=None):
    def f():
        r = requests.get(
            f"{IMD_BASE}/{endpoint}",
            params=params or {},
            timeout=15,
            headers={"User-Agent": "HIMAL-EWS-demo/3.0"},
        )
        r.raise_for_status()
        return r.json()
    return cached("imd:" + endpoint + str(params), f)



def historical_rng(key: str):
    return stable_rng("history:" + key)


def parse_iso_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def make_historical_record(facility, day, index):
    """
    Historical facility snapshot for prototype/demo fields.
    Current public map facts (name/location/type) are treated as static unless
    a timestamped source exists. Operational values are synthetic_demo.
    """
    fid = facility["id"]
    rng = historical_rng(f"{fid}:{day.isoformat()}")
    kind = facility.get("type", "shelter")

    if kind in {"shelter", "potential_shelter"}:
        capacity = int(facility.get("capacity") or 250)
        occupancy = max(0, min(capacity, int(capacity * rng.uniform(0.05, 0.85))))
        available = max(0, capacity - occupancy)
        food = rng.choice([True, True, False])
        water = rng.choice([True, True, True, False])
        return {
            "date": day.date().isoformat(),
            "facility_id": fid,
            "capacity": {"value": capacity, "source": "synthetic_demo"},
            "occupancy": {"value": occupancy, "source": "synthetic_demo"},
            "available_capacity": {"value": available, "source": "synthetic_demo"},
            "usable_space_m2": {
                "value": round(capacity * rng.uniform(3.0, 4.5), 1),
                "source": "synthetic_demo"
            },
            "food_available": {"value": food, "source": "synthetic_demo"},
            "food_servings_estimate": {
                "value": rng.randint(0, max(1, int(capacity * 1.2))) if food else 0,
                "source": "synthetic_demo"
            },
            "water_available": {"value": water, "source": "synthetic_demo"},
            "water_litres_estimate": {
                "value": rng.randint(0, max(1, int(capacity * 15))) if water else 0,
                "source": "synthetic_demo"
            },
            "beds_available": {
                "value": rng.randint(0, max(1, int(available * 0.6))),
                "source": "synthetic_demo"
            },
            "electricity_status": {
                "value": rng.choice(["available", "available", "backup_generator", "limited"]),
                "source": "synthetic_demo"
            },
            "operational_status": {
                "value": rng.choice(["open", "open", "open", "standby", "limited"]),
                "source": "synthetic_demo"
            },
            "medical_support": {
                "value": rng.choice(["none", "basic first-aid", "nurse/first-aid"]),
                "source": "synthetic_demo"
            },
            "provenance": "synthetic_demo"
        }

    beds_total = int(facility.get("capacity") or rng.randint(20, 300))
    beds_available = rng.randint(0, max(1, int(beds_total * 0.6)))
    return {
        "date": day.date().isoformat(),
        "facility_id": fid,
        "beds_total": {"value": beds_total, "source": "synthetic_demo"},
        "beds_available": {"value": beds_available, "source": "synthetic_demo"},
        "occupancy": {"value": beds_total - beds_available, "source": "synthetic_demo"},
        "available_capacity": {"value": beds_available, "source": "synthetic_demo"},
        "usable_space_m2": {
            "value": round(beds_total * rng.uniform(8, 18), 1),
            "source": "synthetic_demo"
        },
        "food_available": {"value": rng.choice([True, True, False]), "source": "synthetic_demo"},
        "water_available": {"value": rng.choice([True, True, True, False]), "source": "synthetic_demo"},
        "water_litres_estimate": {
            "value": rng.randint(1000, 25000),
            "source": "synthetic_demo"
        },
        "oxygen_available": {"value": rng.choice([True, True, False]), "source": "synthetic_demo"},
        "ambulance_available": {"value": rng.choice([True, True, False]), "source": "synthetic_demo"},
        "electricity_status": {
            "value": rng.choice(["available", "available", "backup_generator", "limited"]),
            "source": "synthetic_demo"
        },
        "operational_status": {
            "value": rng.choice(["open", "open", "open", "limited"]),
            "source": "synthetic_demo"
        },
        "provenance": "synthetic_demo"
    }


def make_historical_environment(lat, lon, day):
    """
    Prototype historical environmental series. It is deliberately NOT labelled
    as historical IMD/CWC observations. Real historical government observations
    should replace these series when authenticated archival feeds are connected.
    """
    key = f"{lat:.4f}:{lon:.4f}:{day.date().isoformat()}"
    rng = historical_rng(key)
    rain = round(max(0, rng.gauss(8, 15)), 1)
    river = round(max(0, rng.gauss(2.5, 1.2)), 2)
    return {
        "date": day.date().isoformat(),
        "rainfall_mm": {"value": rain, "source": "synthetic_demo"},
        "river_level_m": {"value": river, "source": "synthetic_demo"},
        "flood_risk_context": {
            "value": "elevated" if rain > 25 or river > 4 else "normal",
            "source": "synthetic_demo"
        },
        "temperature_c": {
            "value": round(rng.gauss(25, 5), 1),
            "source": "synthetic_demo"
        },
        "warning_level": {
            "value": rng.choice(["green", "green", "yellow", "orange"]),
            "source": "synthetic_demo"
        },
        "provenance": "synthetic_demo",
        "warning": "Demo historical series only; not an official IMD/CWC historical observation."
    }


def find_facility_by_id(facility_id: str):
    for x in DEMO:
        if x.get("id") == facility_id:
            return x
    return None



@app.get("/")
def root():
    return {
        "name": "HIMAL-EWS Facility Intelligence API",
        "version": "3.0.0",
        "docs": "/docs",
        "status": "ok",
        "rule": "public data first; synthetic demo values only for unavailable operational fields"
    }


@app.get("/api/v1/facilities")
def facilities(
    lat: float,
    lon: float,
    radius_km: float = Query(10, gt=0, le=100),
    type: Optional[str] = Query(None, pattern="^(shelter|medical|potential_shelter)$"),
    demo_fallback: bool = True,
):
    raw = cached(
        f"osm:{round(lat,3)}:{round(lon,3)}:{round(radius_km,1)}",
        lambda: overpass(lat, lon, radius_km),
    )

    out = []
    if raw is not None:
        for element in raw:
            item = enrich(element, lat, lon)
            if item and (type is None or item["type"] == type):
                out.append(item)

    if not out and demo_fallback:
        for x in DEMO:
            distance = hav(lat, lon, x["latitude"], x["longitude"])
            if distance <= radius_km and (type is None or x["type"] == type):
                y = dict(x)
                y["distance_km"] = round(distance, 2)
                y["data_provenance"] = {k: "synthetic_demo" for k in [
                    "facility_location", "capacity", "occupancy", "available_capacity",
                    "space", "food", "water", "operational_status", "image"
                ]}
                y["demo_warning"] = "DEMO RECORD — replace with verified facility/operator data."
                out.append(y)

    out.sort(key=lambda x: x["distance_km"])

    return {
        "query": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius_km,
            "type": type
        },
        "count": len(out),
        "data_policy": "REAL PUBLIC DATA FIRST; missing operational fields are SYNTHETIC DEMO",
        "data_freshness": "Facility locations are live OSM when Overpass responds; operational fields and historical timelines may be synthetic_demo.",
        "facilities": out,
    }


@app.get("/api/v1/shelters")
def shelters(lat: float, lon: float, radius_km: float = 10):
    return facilities(lat, lon, radius_km, "shelter")


@app.get("/api/v1/medical")
def medical(lat: float, lon: float, radius_km: float = 20):
    return facilities(lat, lon, radius_km, "medical")


@app.get("/api/v1/environment/imd")
def environment_imd(district_id: Optional[int] = None, station_id: Optional[str] = None):
    result = {}
    if station_id:
        result["current_weather"] = imd("current_wx", {"id": station_id})
    else:
        result["current_weather"] = imd("current_wx")
    result["district_warning"] = (
        imd("districtwarning", {"id": district_id}) if district_id else imd("districtwarning")
    )
    result["district_rainfall"] = (
        imd("districtrainfall", {"id": district_id}) if district_id else imd("districtrainfall")
    )
    return {
        "source": "India Meteorological Department (IMD)",
        "live": any(v is not None for v in result.values()),
        "data": result,
        "fallback_note": (
            "This endpoint does not fabricate official IMD observations. "
            "Synthetic operational facility data is handled separately."
        ),
    }



@app.get("/api/v1/historical/facilities")
def historical_facilities(
    lat: float,
    lon: float,
    radius_km: float = Query(10, gt=0, le=100),
    days: int = Query(30, ge=1, le=365),
    type: Optional[str] = Query(None, pattern="^(shelter|medical|potential_shelter)$"),
):
    """
    Historical facility timeline for facilities around a point.
    Live/public facility identity/location is current OSM data; operational
    history is synthetic_demo unless a timestamped operator/government feed exists.
    """
    current = facilities(lat, lon, radius_km, type, True)
    now = datetime.now(timezone.utc)
    history = []
    for f in current["facilities"]:
        series = []
        for i in range(days):
            day = now - timedelta(days=days - 1 - i)
            series.append(make_historical_record(f, day, i))
        history.append({
            "facility_id": f["id"],
            "name": f["name"],
            "type": f["type"],
            "location": f["location"],
            "history": series
        })
    return {
        "query": {"latitude": lat, "longitude": lon, "radius_km": radius_km, "days": days, "type": type},
        "count": len(history),
        "history_policy": "Historical operational fields are synthetic_demo unless an authenticated timestamped source is available.",
        "data": history
    }


@app.get("/api/v1/historical/facility/{facility_id}")
def historical_facility(
    facility_id: str,
    days: int = Query(30, ge=1, le=365),
):
    f = find_facility_by_id(facility_id)
    if not f:
        return {"error": "facility_id not found in demo dataset", "facility_id": facility_id}
    now = datetime.now(timezone.utc)
    series = [
        make_historical_record(f, now - timedelta(days=days - 1 - i), i)
        for i in range(days)
    ]
    return {
        "facility": f,
        "days": days,
        "history": series,
        "provenance": "synthetic_demo",
        "warning": "Replace synthetic history with timestamped operator/government records before real-world use."
    }


@app.get("/api/v1/historical/environment")
def historical_environment(
    lat: float,
    lon: float,
    days: int = Query(30, ge=1, le=365),
):
    now = datetime.now(timezone.utc)
    series = [
        make_historical_environment(lat, lon, now - timedelta(days=days - 1 - i))
        for i in range(days)
    ]
    return {
        "query": {"latitude": lat, "longitude": lon, "days": days},
        "series": series,
        "official_history_sources": [
            "IMD historical/archive products where access is available",
            "CWC/NWIC timestamped river gauge datasets",
            "ISRO Bhuvan historical flood/inundation layers"
        ],
        "warning": "The returned time series is synthetic_demo. It must not be presented as official IMD/CWC observations."
    }



@app.get("/api/v1/intelligence")
def intelligence(
    lat: float,
    lon: float,
    radius_km: float = Query(25, gt=0, le=100),
    days: int = Query(30, ge=1, le=365),
    demo_fallback: bool = True,
):
    """
    SINGLE MASTER ENDPOINT for local/frontend integration.

    It combines current facilities, synthetic operational enrichment,
    historical facility timelines, and historical environmental context.
    It is intentionally self-contained and works locally without requiring
    IMD/CWC credentials for the demo dataset.
    """
    current = facilities(lat, lon, radius_km, None, demo_fallback)

    # Split the combined current list into categories.
    shelters = []
    medical = []
    other = []
    for f in current.get("facilities", []):
        t = f.get("type")
        if t in {"shelter", "potential_shelter"}:
            shelters.append(f)
        elif t == "medical":
            medical.append(f)
        else:
            other.append(f)

    now = datetime.now(timezone.utc)
    facility_history = []
    for f in current.get("facilities", []):
        series = [
            make_historical_record(
                f, now - timedelta(days=days - 1 - i), i
            )
            for i in range(days)
        ]
        facility_history.append({
            "facility_id": f["id"],
            "name": f["name"],
            "type": f["type"],
            "history": series
        })

    environment_history = [
        make_historical_environment(
            lat, lon, now - timedelta(days=days - 1 - i)
        )
        for i in range(days)
    ]

    # Current environment: locally generated demo snapshot. The existing
    # IMD endpoint remains available separately when real public access works.
    current_env = make_historical_environment(lat, lon, now)
    current_env["provenance"] = "synthetic_demo"
    current_env["warning"] = (
        "Local demo snapshot. Connect authenticated/available IMD/CWC feeds "
        "before operational deployment."
    )

    return {
        "api_version": "4.0.0",
        "endpoint": "/api/v1/intelligence",
        "query": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius_km,
            "history_days": days
        },
        "current": {
            "total_facilities": len(current.get("facilities", [])),
            "shelters": shelters,
            "medical": medical,
            "other_nearby_facilities": other
        },
        "historical": {
            "facility_history": facility_history,
            "environment_history": environment_history
        },
        "environment": {
            "current": current_env
        },
        "sources": current.get("sources", []),
        "data_policy": {
            "priority": "REAL PUBLIC DATA FIRST",
            "synthetic_fields": "synthetic_demo",
            "note": (
                "This local demo endpoint never presents simulated operational "
                "values as official government observations."
            )
        },
        "demo_warning": (
            "For SIH/demo use. Facility operational history and current "
            "environment values may be synthetic_demo until timestamped "
            "government/operator feeds are connected."
        )
    }




@app.get("/api/v1/intelligence/optimized")
def intelligence_optimized(
    lat: float,
    lon: float,
    radius_km: float = Query(25, gt=0, le=50),
    days: int = Query(30, ge=1, le=90),
    limit_shelters: int = Query(20, ge=1, le=50),
    limit_medical: int = Query(15, ge=1, le=50),
):
    """
    Lightweight master endpoint for the Antigravity frontend.
    Fetches live public facility locations and returns a ranked, compact
    subset plus historical/demo context. It is designed to avoid the
    10+ MB responses produced by the unrestricted endpoint.
    """
    current = facilities(lat, lon, radius_km, None, True)
    all_facilities = current.get("facilities", [])

    shelters = [f for f in all_facilities if f.get("type") in {"shelter","potential_shelter"}]
    medical = [f for f in all_facilities if f.get("type") == "medical"]

    def shelter_score(f):
        available = float(f.get("available_capacity") or 0)
        cap = float(f.get("capacity") or 1)
        distance = float(f.get("distance_km") or 999)
        food = 1 if f.get("food_available") else 0
        water = 1 if f.get("water_available") else 0
        medical_support = 1 if f.get("medical_support") not in (None, "none") else 0
        operational = 1 if f.get("operational_status") == "open" else 0
        # Capacity and availability dominate; distance is a secondary factor.
        return (
            (available / max(cap,1))*45
            + operational*15
            + water*10
            + food*8
            + medical_support*7
            + max(0, 15 - min(distance,15))
        )

    def medical_score(f):
        beds = float(f.get("beds_available") or f.get("available_capacity") or 0)
        distance = float(f.get("distance_km") or 999)
        oxygen = 1 if f.get("oxygen_available") else 0
        ambulance = 1 if f.get("ambulance_available") else 0
        operational = 1 if f.get("operational_status") == "open" else 0
        return beds*0.2 + oxygen*20 + ambulance*15 + operational*15 + max(0, 15-distance)

    shelters = sorted(shelters, key=shelter_score, reverse=True)[:limit_shelters]
    medical = sorted(medical, key=medical_score, reverse=True)[:limit_medical]

    # Historical data only for the selected facilities, keeping the payload small.
    selected = shelters + medical
    now = datetime.now(timezone.utc)
    facility_history=[]
    for f in selected:
        facility_history.append({
            "facility_id": f["id"],
            "name": f["name"],
            "type": f["type"],
            "history": [
                make_historical_record(f, now - timedelta(days=days-1-i), i)
                for i in range(days)
            ]
        })

    environment_history=[
        make_historical_environment(lat, lon, now - timedelta(days=days-1-i))
        for i in range(days)
    ]

    return {
        "api_version": "5.0.0",
        "endpoint": "/api/v1/intelligence/optimized",
        "query": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius_km,
            "history_days": days
        },
        "summary": {
            "total_found": len(all_facilities),
            "shelters_returned": len(shelters),
            "medical_returned": len(medical),
            "optimized_for_frontend": True
        },
        "recommended_shelters": shelters,
        "medical_facilities": medical,
        "historical": {
            "selected_facilities": facility_history,
            "environment": environment_history
        },
        "environment": {
            "current": make_historical_environment(lat, lon, now)
        },
        "sources": current.get("sources", []),
        "data_policy": {
            "live_public": "Facility identity/location where OSM/Overpass responds",
            "synthetic_demo": "Operational capacity, occupancy, food, water and historical values when authoritative timestamped feeds are unavailable"
        }
    }



@app.get("/api/v1/history")
def history(
    lat: float,
    lon: float,
    radius_km: float = Query(10, gt=0, le=100),
    days: int = Query(30, ge=1, le=365),
    type: Optional[str] = Query(None, pattern="^(shelter|medical|potential_shelter)$"),
):
    """
    One-call historical bundle for the Antigravity frontend:
    facilities + environmental context.
    """
    facility_history = historical_facilities(lat, lon, radius_km, days, type)
    environment_history = historical_environment(lat, lon, days)
    return {
        "query": {"latitude": lat, "longitude": lon, "radius_km": radius_km, "days": days, "type": type},
        "facility_history": facility_history["data"],
        "environment_history": environment_history["series"],
        "data_policy": "REAL PUBLIC DATA FIRST; unavailable historical operational fields are synthetic_demo.",
        "demo_warning": "Historical facility operations and environmental series in this prototype are simulated. Replace with timestamped official/operator archives before operational deployment."
    }



@app.get("/api/v1/demo")
def demo():
    return {
        "warning": "DEMO DATA ONLY — not for real evacuation decisions",
        "facilities": DEMO
    }


@app.get("/api/v1/sources")
def sources():
    return {
        "policy": "Use authoritative/public data first. If a field is unavailable live, return a synthetic_demo value and label it.",
        "sources": [
            {
                "name": "OpenStreetMap / Overpass",
                "role": "Live geospatial facility locations, tags, some contact/image/capacity metadata",
                "url": "https://wiki.openstreetmap.org/wiki/Overpass_API",
                "status": "live query"
            },
            {
                "name": "India Meteorological Department",
                "role": "Weather, district rainfall and warning context",
                "url": "https://api.imd.gov.in/public/api_reference.html",
                "status": "live when IMD API responds"
            },
            {
                "name": "data.gov.in National Hospital Directory",
                "role": "Government hospital directory / geocoded facility data",
                "url": "https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month",
                "status": "public government dataset; can be loaded as a scheduled database layer"
            },
            {
                "name": "ISRO Bhuvan",
                "role": "Indian earth-observation and geospatial context",
                "url": "https://bhuvan-app1.nrsc.gov.in/api/",
                "status": "public platform; product/API access varies"
            },
            {
                "name": "CWC / NWIC",
                "role": "River/flood observation and forecast context",
                "url": "https://cwc.gov.in/",
                "status": "government source; product feeds vary"
            },
            {
                "name": "Synthetic demo enrichment",
                "role": "Occupancy, available capacity, usable space, food/water stock, beds, operational status and other fields not exposed as live nationwide data",
                "status": "SYNTHETIC — explicitly labelled in every record"
            }
        ]
    }

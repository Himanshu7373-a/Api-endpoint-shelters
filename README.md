# HIMAL-EWS Facility Intelligence API v3

## What this version does

This API follows the requested rule:

> **Use real/public data wherever available. If a field cannot be obtained live, fill it with synthetic demo data in the same API record and clearly label it `synthetic_demo`.**

### Facility data

For a target latitude/longitude and radius, `/api/v1/facilities` queries OpenStreetMap/Overpass live.

It returns:

- shelter / potential shelter / medical facility
- live latitude + longitude
- distance from target
- address
- phone and website where mapped
- image URL (real OSM/Wikimedia image when available, otherwise a clearly synthetic placeholder)
- capacity
- current occupancy (synthetic when no live feed exists)
- available capacity
- usable space
- food availability
- estimated food servings
- water availability
- estimated water litres
- beds available for medical facilities
- electricity status
- operational status
- medical support
- ambulance / oxygen flags for medical facilities
- per-field provenance

## Important

Synthetic values are **demo values, not real emergency information**. They are included so the Antigravity prototype has complete records instead of empty fields.

Before real deployment, synthetic fields should be replaced with authenticated feeds from shelter operators, district authorities, hospitals, disaster-management authorities, etc.

## Endpoints

### All facilities

`GET /api/v1/facilities?lat=30.3165&lon=78.0322&radius_km=25`

Optional:

`&type=shelter`

`&type=medical`

`&type=potential_shelter`

### Shelters

`GET /api/v1/shelters?lat=30.3165&lon=78.0322&radius_km=25`

### Medical

`GET /api/v1/medical?lat=30.3165&lon=78.0322&radius_km=25`

### IMD context

`GET /api/v1/environment/imd`

### Sources

`GET /api/v1/sources`

### Demo records

`GET /api/v1/demo`

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger:

`http://localhost:8000/docs`

## Antigravity

If Antigravity and this API are running on the same machine:

`http://localhost:8000/api/v1/facilities?lat=30.3165&lon=78.0322&radius_km=25`

If Antigravity is deployed online, deploy this API and replace `localhost` with the public API domain.


## Historical data (v3)

The API now includes historical endpoints so the Antigravity frontend can display time-series charts and historical facility status.

### 1. Historical facility data
`GET /api/v1/historical/facilities?lat=30.3165&lon=78.0322&radius_km=25&days=30`

Returns a daily timeline for every nearby shelter/medical facility covering:
- capacity
- occupancy
- available capacity
- usable space
- food availability / estimated servings
- water availability / estimated litres
- beds / bed availability
- electricity
- operational status
- medical support
- explicit `source: synthetic_demo` where the history is simulated

### 2. One facility's history
`GET /api/v1/historical/facility/{facility_id}?days=90`

### 3. Historical environmental context
`GET /api/v1/historical/environment?lat=30.3165&lon=78.0322&days=30`

Includes a time series structure for rainfall, river level, warning level, temperature and flood-risk context. **In this prototype those historical values are synthetic_demo**; they are not represented as official IMD/CWC observations.

### 4. Combined history endpoint
`GET /api/v1/history?lat=30.3165&lon=78.0322&radius_km=25&days=30`

This is the easiest endpoint for Antigravity: it returns both facility history and environmental history in one response.

### Historical-data provenance rule

Do not mix simulated history with official history. Every historical record is labelled `synthetic_demo` until authenticated timestamped archives are connected.

The intended production priority is:
1. Timestamped operator/authority shelter logs for occupancy, food, water, beds, power and operational status.
2. CWC/NWIC timestamped river gauge/discharge archives.
3. IMD historical/archive rainfall and warning products.
4. ISRO Bhuvan historical flood/inundation layers.
5. OSM/history only for static facility metadata and mapping, not operational occupancy.

### Frontend recommendation

Use `/api/v1/history` for a "History" tab with:
- occupancy vs capacity
- available beds
- food/water availability
- operational status
- rainfall
- river level
- warning level

Clearly show a `DEMO / SYNTHETIC` badge for any synthetic series.


## ONE local master endpoint

For Antigravity, use this single endpoint:

`GET http://127.0.0.1:8000/api/v1/intelligence?lat=30.3165&lon=78.0322&radius_km=25&days=30`

Equivalent:

`GET http://localhost:8000/api/v1/intelligence?lat=30.3165&lon=78.0322&radius_km=25&days=30`

It combines:
- nearby shelters
- nearby medical facilities
- other nearby facilities
- coordinates and distance
- images
- capacity / occupancy / available capacity
- usable space
- food
- water
- beds
- electricity
- operational status
- medical support
- current environmental demo snapshot
- historical facility series
- historical environmental series
- source/provenance and synthetic-data warnings

### Run locally

From the folder containing `app/main.py`:

`pip install -r requirements.txt`

`uvicorn app.main:app --host 127.0.0.1 --port 8000`

Then test:

`http://127.0.0.1:8000/docs`

and the master endpoint above.

### Important

`ECONNREFUSED 127.0.0.1:8000` means nothing is listening on port 8000. It is not a query-parameter problem. Start the FastAPI server first.

If Antigravity itself is serving the frontend on another port, keep this API server running separately on 8000, or proxy `/api` from the frontend to this backend.


## Antigravity frontend endpoint (recommended)

Use this lightweight master endpoint instead of `/api/v1/intelligence`:

`http://127.0.0.1:8000/api/v1/intelligence/optimized?lat=30.3165&lon=78.0322&radius_km=25&days=30`

It returns a compact payload containing:
- ranked/recommended shelters
- medical facilities
- live public facility coordinates
- distance
- capacity/occupancy/available capacity
- space
- food/water
- beds
- electricity/operations
- images
- 30-day historical facility data
- 30-day historical environmental data
- current environmental context
- source/provenance information

The endpoint limits the default response to 20 shelters + 15 medical facilities, which is much more suitable for a frontend than returning hundreds of facilities.

### Antigravity integration

The frontend can call:

`fetch("http://127.0.0.1:8000/api/v1/intelligence/optimized?lat=30.3165&lon=78.0322&radius_km=25&days=30")`

Do not hard-code the example coordinates in production. Replace them with the map/user-selected coordinates.

If the browser blocks the request, make sure the API server is running and the frontend is also running on the same laptop. The API's demo CORS is open.

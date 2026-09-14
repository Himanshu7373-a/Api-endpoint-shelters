# HIMAL-EWS Data Policy

## Three provenance classes

- `real_public`: obtained from a public source such as OpenStreetMap/Overpass or an accessible government API.
- `estimated`: derived mathematically from a real field (for example distance from coordinates).
- `synthetic_demo`: simulated because no reliable nationwide live feed exposes the field.

## Synthetic fields

The prototype may simulate:

- occupancy
- available capacity
- usable space
- food stock / servings
- water stock / litres
- beds available
- electricity status
- operational status
- oxygen / ambulance availability
- medical support level

These values are deterministic per facility so the demo does not randomly change every refresh.

## Never present synthetic values as live government data

The frontend should show a small `DEMO / SIMULATED` badge beside synthetic fields.


## Historical-data policy

Historical data is separated from current live data. A historical value is only marked real when it comes from a timestamped authoritative/public archive or an authenticated facility/operator log. Otherwise it is `synthetic_demo`.

For the prototype, the historical endpoints intentionally generate deterministic daily values for unavailable fields so charts, trends and the HIMAL-EWS action layer can be demonstrated without falsely claiming that the values came from IMD/CWC or a shelter operator.

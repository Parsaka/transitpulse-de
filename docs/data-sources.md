# Data sources and licences

| Dataset | Provider | Endpoint | Licence | Notes |
|---|---|---|---|---|
| GTFS-Realtime VBB (TripUpdates) | Verkehrsverbund Berlin-Brandenburg (OpenDataVBB) | `https://production.gtfsrt.vbb.de/data` | CC BY 4.0 | No auth; limit 60 req/min; informative User-Agent required; ETag supported. Provider notes reduced coverage since 2026-06-04. Measured 2026-10-22: 6.3 MB per fetch, 6,455 trip updates, 353 routes, 124k stop-time updates. |
| GTFS static VBB | VBB | `https://unternehmen.vbb.de/gtfs` (zip, updated twice a week; archive 2010-2024 on the same page) | CC BY 4.0 | Needed for stops, routes, agencies, calendar; the weekly job lands it in the Volume. |
| GTFS-Realtime Germany (TripUpdates, ServiceAlerts) | gtfs.de (BETA) | `https://realtime.gtfs.de/realtime-free.pb` | CC BY-SA 4.0 (per-operator terms listed on gtfs.de) | Updated every 10 s. Measured 2026-10-22: 8.3 MB, 24,957 trip updates, 374 alerts; `route_id` empty, join on `trip_id` with the gtfs.de static feed. |
| GTFS static Germany | gtfs.de / DELFI | `https://gtfs.de/de/feeds/` | CC BY 4.0 | Nationwide schedule. |
| Weather, hourly (observed + 2-day forecast) | Open-Meteo (ERA5/ICON based) | `https://api.open-meteo.com/v1/forecast` | CC BY 4.0 (free for non-commercial use, no key) | Nine grid points over Berlin-Brandenburg, fetched hourly by the Function (`weather` timer) with `past_days=2`; one-off backfill `past_days=92`. Rows carry `is_forecast`. Stops are joined to the nearest point (`dim_stop_weather_point`). Bright Sky/DWD is kept as the alternative. |

Attribution text for the project page: "Fahrplan- und Echtzeitdaten: VBB (CC BY 4.0), gtfs.de
(CC BY-SA 4.0); Wetterdaten: Open-Meteo.com (CC BY 4.0)."

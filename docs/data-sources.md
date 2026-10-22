# Data sources and licences

| Dataset | Provider | Endpoint | Licence | Notes |
|---|---|---|---|---|
| GTFS-Realtime VBB (TripUpdates) | Verkehrsverbund Berlin-Brandenburg (OpenDataVBB) | `https://production.gtfsrt.vbb.de/data` | CC BY 4.0 | No auth; limit 60 req/min; informative User-Agent required; ETag supported. Provider notes reduced coverage since 2026-06-04. Measured 2026-10-22: 6.3 MB per fetch, 6,455 trip updates, 353 routes, 124k stop-time updates. |
| GTFS static VBB | VBB | `https://www.vbb.de/vbb-services/api-open-data/datensaetze/` | CC BY 4.0 | Weekly refresh; needed for stops, routes, agencies. |
| GTFS-Realtime Germany (TripUpdates, ServiceAlerts) | gtfs.de (BETA) | `https://realtime.gtfs.de/realtime-free.pb` | CC BY-SA 4.0 (per-operator terms listed on gtfs.de) | Updated every 10 s. Measured 2026-10-22: 8.3 MB, 24,957 trip updates, 374 alerts; `route_id` empty, join on `trip_id` with the gtfs.de static feed. |
| GTFS static Germany | gtfs.de / DELFI | `https://gtfs.de/de/feeds/` | CC BY 4.0 | Nationwide schedule. |
| Weather observations and forecasts | DWD via Bright Sky, Open-Meteo | `https://api.brightsky.dev`, `https://api.open-meteo.com` | DWD: DL-DE/BY-2.0; Open-Meteo: CC BY 4.0 | Hourly, for station locations. |

Attribution text for the project page: "Fahrplan- und Echtzeitdaten: VBB (CC BY 4.0), gtfs.de
(CC BY-SA 4.0); Wetterdaten: Deutscher Wetterdienst."

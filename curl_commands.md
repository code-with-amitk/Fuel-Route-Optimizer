# Route API — curl test commands

Start the server first:

```bash
cd /home/amit/Fuel-Route-Optimizer
source .venv/bin/activate
python manage.py runserver
```

Optional: pipe through `python -m json.tool` for readable JSON (responses can be large).

Base URL: `http://127.0.0.1:8000/api/v1/route/`

---

## Success scenarios

### 1. Short trip — no fuel stops (< 500 mi)

Address-based (2 geocode + 1 route = **3 ORS calls**).

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Milwaukee, WI"}' \
  | python -m json.tool | grep -A6 '"summary"'
```

**Expected:** `200`, ~90–95 mi, `fuel_stops_count: 0`, `total_fuel_cost_usd: 0.0`  
*(Cost is $0 because no refuel stops are needed; see architecture cost model.)*

---

### 2. Medium trip — may still have 0 stops (under 500 mi)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Denver, CO"}' \
  | python -m json.tool | grep -E '"summary"|"fuel_stops"|"name"|"leg_fuel_cost'
```

**Expected:** `200`, ~920–1000 mi — if under 500 mi logic doesn't apply; Denver is ~1000 mi so **expect multiple fuel stops** and non-zero cost.

---

### 3. Long cross-country — multiple fuel stops (> 500 mi)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "New York, NY", "finish": "Los Angeles, CA"}' \
  | python -m json.tool | grep -A8 '"summary"'
```

**Expected:** `200`, ~2800 mi, `fuel_stops_count` ≥ 4, `total_fuel_cost_usd` > 0.  
*(Slow: 3 ORS calls + optimizer over long polyline.)*

```
Response:
"summary": {
    "total_distance_miles": 2797.5,
    "total_fuel_cost_usd": 750.12,
    "fuel_stops_count": 13,
    "mpg": 10,
    "max_range_miles": 500
}
```

---

### 4. Classic assessment route — Chicago to Los Angeles

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Los Angeles, CA"}' \
  | python -m json.tool | grep -A8 '"summary"'
```

**Expected:** `200`, ~2000 mi, several fuel stops, non-zero total cost.

```
Response:
"summary": {
    "total_distance_miles": 2797.5,
    "total_fuel_cost_usd": 750.12,
    "fuel_stops_count": 13,
    "mpg": 10,
    "max_range_miles": 500
}
```

---

### 5. Coordinates only — skip geocoding (**1 ORS call**)

Use when you already have lat/lng (faster, no address lookup).

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"lat": 41.8781, "lng": -87.6298},
    "finish": {"lat": 43.0389, "lng": -87.9065}
  }' | python -m json.tool | grep -A6 '"summary"'
```

**Expected:** `200`, Chicago → Milwaukee ~92 mi, 0 fuel stops.

```
Response:
"summary": {
        "total_distance_miles": 92.1,
        "total_fuel_cost_usd": 0.0,
        "fuel_stops_count": 0,
        "mpg": 10,
        "max_range_miles": 500
    }
```

---

### 6. Long trip with coordinates only (LA from Chicago coords)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"lat": 41.8781, "lng": -87.6298},
    "finish": {"lat": 34.0522, "lng": -118.2437}
  }' | python -m json.tool | grep -A8 '"summary"'
```

**Expected:** `200`, ~2000 mi, multiple fuel stops.

```
Response:
"summary": {
        "total_distance_miles": 2015.0,
        "total_fuel_cost_usd": 587.8,
        "fuel_stops_count": 11,
        "mpg": 10,
        "max_range_miles": 500
    }
```

---

### 7. Mixed input — address start, coordinate finish

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": "Chicago, IL",
    "finish": {"lat": 43.0389, "lng": -87.9065}
  }' | python -m json.tool | grep -A6 '"summary"'
```

**Expected:** `200`, 1 geocode + 1 route.

---

### 8. Same start and finish — minimal trip

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Chicago, IL"}' \
  | python -m json.tool | grep -A6 '"summary"'
```

**Expected:** `200`, ~0 mi, 0 fuel stops, $0 cost.

---

### 9. GET with address query params (browser-friendly)

```bash
curl -sG "http://127.0.0.1:8000/api/v1/route/" \
  --data-urlencode "start=Chicago, IL" \
  --data-urlencode "finish=Milwaukee, WI" \
  | python -m json.tool | grep -A6 '"summary"'
```

**Expected:** `200`, same as POST example 1.

---

### 10. GET with JSON coordinates in query string

```bash
curl -sG "http://127.0.0.1:8000/api/v1/route/" \
  --data-urlencode 'start={"lat": 41.8781, "lng": -87.6298}' \
  --data-urlencode 'finish={"lat": 43.0389, "lng": -87.9065}' \
  | python -m json.tool | grep -A6 '"summary"'
```

**Expected:** `200`, coordinate-based short trip.

---

### 11. Full response to file (long routes produce huge polylines)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Milwaukee, WI"}' \
  -o /tmp/route_response.json

python -m json.tool /tmp/route_response.json | head -40
```

---

### 12. Inspect fuel stops only (long route)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Denver, CO"}' \
  | python -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('fuel_stops', []):
    print(f\"{s['name'][:40]:40} {s['state']}  \${s['retail_price']:.3f}  mile {s['distance_from_start_miles']}  leg \${s['leg_fuel_cost_usd']:.2f}\")
print('TOTAL', d['summary']['total_fuel_cost_usd'])
"
```

---

## Error scenarios

### 13. Missing `finish` — 400

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL"}'
```

**Expected:** `400`, validation error.

---

### 14. Empty address — 400

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "", "finish": "Chicago, IL"}'
```

**Expected:** `400`.

---

### 15. Invalid coordinates (missing lng) — 400

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": {"lat": 41.88}, "finish": "Chicago, IL"}'
```

**Expected:** `400`.

---

### 16. Geocode miss — 404

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Xyznotaplace, ZZ", "finish": "Chicago, IL"}'
```

**Expected:** `404`, no geocoding match.

---

### 17. Outside USA coordinates — 400

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"lat": 51.5074, "lng": -0.1278},
    "finish": {"lat": 41.8781, "lng": -87.6298}
  }'
```

**Expected:** `400`, London coords outside USA bounds.

---

### 18. GET missing query params — 400

```bash
curl -s -w "\nHTTP %{http_code}\n" "http://127.0.0.1:8000/api/v1/route/?start=Chicago"
```

**Expected:** `400`, `'finish' is required`.

---

### 19. Malformed JSON — 400

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish":'
```

**Expected:** `400`, parse error.

---

## Automated client (all-in-one)

With the server running:

```bash
python manage.py test_route_api
python manage.py test_route_api --base-url http://127.0.0.1:8000
```

---

## Quick reference — ORS call count

| Request type | ORS calls |
|---|---|
| Both addresses | 2 geocode + 1 route = **3** |
| Both coordinates | **1** route only |
| One address + one coordinate | 1 geocode + 1 route = **2** |

Ensure `.env` has a valid `ORS_API_KEY`.

# Fuel-Route-Optimizer

- This is *Django REST API* that accepts a USA start and finish location, returns a driving route map, recommends cost-optimal fuel stops along that route (500-mile vehicle range, 10 MPG), and computes total fuel spend using `fuel-prices-for-be-assessment.csv`.
- Clients (web app, mobile app, curl, Postman, another service) send HTTP requests and receive JSON responses containing:
-- Route polyline / GeoJSON
-- Fuel stop recommendations with prices
-- Total fuel cost
- Fuel prices are given in fuel-prices-for-be-assessment.csv given in following format, it does not have no latitude/longitude. The CSV has addresses but **no coordinates**. We need coordinates to match stations to points along the route. We will get (lat, long) of truckstop offline and store in Database, to save time for online query.
```
OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
```

## Documentation
- [1. Getting Started](./Documentation/1.%20Getting_Started.md)
- [2. Fuel Station Table](./Documentation/2.%20FuelStation_Table.md)
- [3. Distance Between Points](./Documentation/3.%20Distance_Between_Points.md)
- [4. Greedy fuel stop optimizer and cost calculator](./Documentation/4.%20Greedy%20fuel%20stop%20optimizer%20and%20cost%20calculator.md)
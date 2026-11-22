-- One row per PIN code.
--   prefix point = median lat/lon of all in-box offices sharing a 3-digit prefix
--   offices more than {PREFIX_OUTLIER_KM} km from their prefix point are dropped
--   point       = median lat/lon of what remains
--   spread_km   = furthest remaining office from that point
--   trusted     = spread_km < {PIN_TIGHT_KM}
CREATE OR REPLACE TABLE {T_PIN_POINT} AS
WITH office AS (
  SELECT lpad(CAST(pincode AS STRING), 6, '0')             AS pin,
         substr(lpad(CAST(pincode AS STRING), 6, '0'), 1, 3) AS prefix,
         try_cast(latitude  AS DOUBLE)                     AS lat,
         try_cast(longitude AS DOUBLE)                     AS lon
  FROM {T_PINCODE}
),
in_box AS (
  SELECT * FROM office
  WHERE lat BETWEEN {LAT_MIN} AND {LAT_MAX}
    AND lon BETWEEN {LON_MIN} AND {LON_MAX}
),
prefix_point AS (
  SELECT prefix, median(lat) AS plat, median(lon) AS plon
  FROM in_box GROUP BY prefix
),
kept AS (
  SELECT b.pin, b.lat, b.lon
  FROM in_box b JOIN prefix_point p USING (prefix)
  WHERE {F_HAVERSINE}(b.lat, b.lon, p.plat, p.plon) <= {PREFIX_OUTLIER_KM}
),
point AS (
  SELECT pin, median(lat) AS lat, median(lon) AS lon, count(*) AS n_offices
  FROM kept GROUP BY pin
)
SELECT p.pin,
       p.lat,
       p.lon,
       p.n_offices,
       max({F_HAVERSINE}(k.lat, k.lon, p.lat, p.lon))                       AS spread_km,
       max({F_HAVERSINE}(k.lat, k.lon, p.lat, p.lon)) < {PIN_TIGHT_KM}      AS trusted
FROM point p JOIN kept k USING (pin)
GROUP BY p.pin, p.lat, p.lon, p.n_offices;

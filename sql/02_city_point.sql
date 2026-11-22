-- One row per city name, from the facilities that already have good coordinates.
-- Only cities with at least {MIN_CITY_FACILITIES} such facilities are kept.
CREATE OR REPLACE TABLE {T_CITY_POINT} AS
WITH dedup AS (
  SELECT * FROM (
    SELECT unique_id, address_city, latitude, longitude,
           row_number() OVER (PARTITION BY unique_id ORDER BY name) AS rn
    FROM {T_FACILITIES}
  ) WHERE rn = 1
),
usable AS (
  SELECT lower(trim(address_city)) AS city_key, latitude AS lat, longitude AS lon
  FROM dedup
  WHERE address_city IS NOT NULL AND trim(address_city) <> ''
    AND latitude  BETWEEN {LAT_MIN} AND {LAT_MAX}
    AND longitude BETWEEN {LON_MIN} AND {LON_MAX}
)
SELECT city_key,
       median(lat) AS lat,
       median(lon) AS lon,
       count(*)    AS n_facilities
FROM usable
GROUP BY city_key
HAVING count(*) >= {MIN_CITY_FACILITIES};

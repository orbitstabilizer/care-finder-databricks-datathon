-- One row per facility. Picks the point to show and says how much to trust it.
-- A check "passes" when the distance is under {NEAR_KM} km.
-- The PIN point is only used as a check when pin_point.trusted. An untrusted
-- PIN point is still used as a weaker check, with the threshold widened by that
-- PIN's own spread_km (rules 9 and 10).
CREATE OR REPLACE TABLE {T_FAC_LOC} AS
WITH dedup AS (
  SELECT * FROM (
    SELECT f.*, row_number() OVER (PARTITION BY unique_id ORDER BY name) AS rn
    FROM {T_FACILITIES} f
  ) WHERE rn = 1
),
base AS (
  SELECT
    unique_id AS facility_id,
    name,
    nullif(trim(concat_ws(', ',
      nullif(trim(address_line1), ''), nullif(trim(address_line2), ''),
      nullif(trim(address_line3), ''))), '')            AS address,
    address_city                                        AS city,
    address_stateOrRegion                               AS state,
    nullif(trim(address_zipOrPostcode), '')             AS postcode,
    latitude  AS raw_lat,
    longitude AS raw_lon,
    lower(trim(address_city))                           AS city_key,
    -- first 6 consecutive digits found in the postcode field
    regexp_extract(regexp_replace(coalesce(address_zipOrPostcode, ''), '[^0-9]', ''),
                   '^([0-9]{{6}})', 1)                  AS pin
  FROM dedup
),
joined AS (
  SELECT
    b.facility_id, b.name, b.address, b.city, b.state, b.postcode,
    b.raw_lat, b.raw_lon,
    CASE WHEN p.trusted     THEN p.lat END AS pin_lat,
    CASE WHEN p.trusted     THEN p.lon END AS pin_lon,
    CASE WHEN NOT p.trusted THEN p.lat END AS weak_pin_lat,
    CASE WHEN NOT p.trusted THEN p.lon END AS weak_pin_lon,
    CASE WHEN NOT p.trusted THEN p.spread_km END AS weak_pin_spread_km,
    c.lat AS city_lat,
    c.lon AS city_lon,
    -- latitude/longitude are NULL for most unplaceable rows, and NULL BETWEEN ...
    -- is NULL, not false. Without the coalesce, NOT raw_ok never fires and every
    -- such row falls through to the "nothing usable" rule.
    coalesce(b.raw_lat BETWEEN {LAT_MIN} AND {LAT_MAX}
         AND b.raw_lon BETWEEN {LON_MIN} AND {LON_MAX}, false) AS raw_ok
  FROM base b
  LEFT JOIN {T_PIN_POINT}  p ON b.pin = p.pin AND b.pin <> ''
  LEFT JOIN {T_CITY_POINT} c ON b.city_key = c.city_key
),
dist AS (
  SELECT j.*,
    CASE WHEN raw_ok AND pin_lat  IS NOT NULL THEN {F_HAVERSINE}(raw_lat, raw_lon, pin_lat,  pin_lon)  END AS d_pin_km,
    CASE WHEN raw_ok AND city_lat IS NOT NULL THEN {F_HAVERSINE}(raw_lat, raw_lon, city_lat, city_lon) END AS d_city_km,
    CASE WHEN raw_ok AND weak_pin_lat IS NOT NULL THEN {F_HAVERSINE}(raw_lat, raw_lon, weak_pin_lat, weak_pin_lon) END AS d_weak_pin_km,
    CASE WHEN pin_lat IS NOT NULL AND city_lat IS NOT NULL
         THEN {F_HAVERSINE}(pin_lat, pin_lon, city_lat, city_lon) END AS d_pin_city_km
  FROM joined j
),
flagged AS (
  SELECT d.*,
    (CASE WHEN pin_lat  IS NOT NULL THEN 1 ELSE 0 END)
  + (CASE WHEN city_lat IS NOT NULL THEN 1 ELSE 0 END)                       AS n_checks,
    (CASE WHEN d_pin_km  < {NEAR_KM} THEN 1 ELSE 0 END)
  + (CASE WHEN d_city_km < {NEAR_KM} THEN 1 ELSE 0 END)                      AS n_pass,
    coalesce(d_weak_pin_km < {NEAR_KM} + weak_pin_spread_km, false)          AS weak_pin_pass
  FROM dist d
),
ruled AS (
  SELECT f.*,
    CASE
      WHEN raw_ok AND n_checks = 2 AND n_pass = 2                              THEN 1
      WHEN raw_ok AND n_pass >= 1                                              THEN 2
      WHEN raw_ok AND n_checks = 2 AND n_pass = 0
           AND d_pin_city_km < {NEAR_KM}                                       THEN 3
      -- weak PIN rescue: only reachable when the PIN point exists but is untrusted
      WHEN raw_ok AND weak_pin_lat IS NOT NULL AND weak_pin_pass               THEN 9
      WHEN raw_ok AND n_checks >= 1 AND n_pass = 0                             THEN 4
      WHEN raw_ok AND n_checks = 0 AND weak_pin_lat IS NOT NULL                THEN 10
      WHEN raw_ok AND n_checks = 0                                             THEN 5
      WHEN NOT raw_ok AND pin_lat  IS NOT NULL                                 THEN 6
      WHEN NOT raw_ok AND city_lat IS NOT NULL                                 THEN 7
      ELSE 8
    END AS rule_id
  FROM flagged f
)
SELECT
  facility_id, name, address, city, state, postcode,
  raw_lat, raw_lon, pin_lat, pin_lon, city_lat, city_lon,
  weak_pin_lat, weak_pin_lon, weak_pin_spread_km,
  d_pin_km, d_city_km, d_weak_pin_km,
  CASE rule_id WHEN 3 THEN city_lat WHEN 6 THEN pin_lat WHEN 7 THEN city_lat
               WHEN 8 THEN CAST(NULL AS DOUBLE) ELSE raw_lat END AS final_lat,
  CASE rule_id WHEN 3 THEN city_lon WHEN 6 THEN pin_lon WHEN 7 THEN city_lon
               WHEN 8 THEN CAST(NULL AS DOUBLE) ELSE raw_lon END AS final_lon,
  CASE rule_id WHEN 3 THEN 'city_point' WHEN 6 THEN 'pin_point'
               WHEN 7 THEN 'city_point' WHEN 8 THEN 'none'
               ELSE 'coordinates' END                            AS location_source,
  CASE rule_id WHEN 1 THEN 'high'        WHEN 2 THEN 'good'
               WHEN 3 THEN 'approximate' WHEN 4 THEN 'suspect'
               WHEN 5 THEN 'unverified'  WHEN 6 THEN 'approximate'
               WHEN 7 THEN 'approximate' WHEN 9 THEN 'good'
               WHEN 10 THEN 'suspect'    ELSE 'none' END         AS location_confidence,
  CASE rule_id
    WHEN 1 THEN 'Listed coordinates agree with both the postcode and the city.'
    WHEN 2 THEN 'Listed coordinates agree with the postcode or the city.'
    WHEN 3 THEN 'Listed coordinates conflict with the postcode and city. Showing city centre.'
    WHEN 4 THEN 'Listed coordinates do not match the postcode or city on record. Position may be wrong.'
    WHEN 5 THEN 'Listed coordinates could not be cross-checked against any postcode or city.'
    WHEN 6 THEN 'No usable coordinates. Showing the centre of the postcode area.'
    WHEN 7 THEN 'No usable coordinates. Showing the city centre.'
    WHEN 9 THEN concat('Listed coordinates agree with the postcode area, which is wide (about ',
                       cast(round(weak_pin_spread_km) AS INT), ' km across), so this is a loose check.')
    WHEN 10 THEN concat('The only cross-check available was a wide postcode area (about ',
                        cast(round(weak_pin_spread_km) AS INT),
                        ' km across) and the coordinates fall outside even that. Position may be wrong.')
    ELSE 'No usable coordinates, postcode or city. This facility cannot be placed on the map.'
  END                                                            AS location_note,
  rule_id
FROM ruled;

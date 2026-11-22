-- District context for one search: workspace.vf NFHS first step (scripts/build_nfhs.py builds the tables).
-- Named parameters: :lat DOUBLE, :lon DOUBLE (search point; may be NULL if :pin is given),
--                   :pin STRING (6 digits or NULL), :service STRING (service label, e.g. 'dialysis').
-- District choice: the PIN's primary district if :pin is in the PIN directory ('from_pin'), otherwise the
-- primary district of the nearest trusted PIN centre to the point ('nearest_pin_centre', approximate).
-- Returns one row. NFHS values are context, not evidence; counts are "in our data".
WITH params AS (
  SELECT CAST(:lat AS DOUBLE) AS lat, CAST(:lon AS DOUBLE) AS lon,
         CAST(:pin AS STRING) AS pin, CAST(:service AS STRING) AS service
),
pin_hit AS (
  SELECT d.*, 'from_pin' AS district_method, CAST(NULL AS DOUBLE) AS pin_centre_km
  FROM workspace.vf.pin_district d JOIN params p ON d.pin = p.pin
  WHERE d.is_primary
),
nearest_pin AS (
  SELECT pp.pin, workspace.vf.haversine_km(p.lat, p.lon, pp.lat, pp.lon) AS km
  FROM workspace.vf.pin_point pp CROSS JOIN params p
  WHERE pp.trusted AND p.lat IS NOT NULL
    AND pp.lat BETWEEN p.lat - 1.5 AND p.lat + 1.5 AND pp.lon BETWEEN p.lon - 1.5 AND p.lon + 1.5
  ORDER BY km LIMIT 1
),
near_hit AS (
  SELECT d.*, 'nearest_pin_centre' AS district_method, n.km AS pin_centre_km
  FROM workspace.vf.pin_district d JOIN nearest_pin n ON d.pin = n.pin
  WHERE d.is_primary
),
chosen AS (
  SELECT * FROM pin_hit
  UNION ALL
  SELECT * FROM near_hit WHERE NOT EXISTS (SELECT 1 FROM pin_hit)
),
-- search point: the given coordinates, else the PIN centre
point AS (
  SELECT coalesce(p.lat, pp.lat) AS lat, coalesce(p.lon, pp.lon) AS lon,
         CASE WHEN p.lat IS NOT NULL THEN 'given' WHEN pp.lat IS NOT NULL THEN 'pin_centre' END AS point_source
  FROM params p LEFT JOIN workspace.vf.pin_point pp ON pp.pin = p.pin
),
nfhs AS (
  SELECT n.* FROM workspace.vf.nfhs_district n JOIN chosen c ON n.nfhs_key = c.nfhs_key
),
long AS (
  SELECT nfhs_key, indicator_column, value, rank_of_706, quartile FROM nfhs
  UNPIVOT ((value, rank_of_706, quartile) FOR indicator_column IN (
    (m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct, rank_m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct, quartile_m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct) AS m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct,
    (w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct, rank_w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct, quartile_w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct) AS w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct,
    (m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct, rank_m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct, quartile_m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct) AS m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct,
    (births_delivered_by_csection_5y_pct, rank_births_delivered_by_csection_5y_pct, quartile_births_delivered_by_csection_5y_pct) AS births_delivered_by_csection_5y_pct,
    (institutional_birth_5y_pct, rank_institutional_birth_5y_pct, quartile_institutional_birth_5y_pct) AS institutional_birth_5y_pct,
    (births_attended_by_skilled_hp_5y_10_pct, rank_births_attended_by_skilled_hp_5y_10_pct, quartile_births_attended_by_skilled_hp_5y_10_pct) AS births_attended_by_skilled_hp_5y_10_pct,
    (all_w15_49_who_are_anaemic_pct, rank_all_w15_49_who_are_anaemic_pct, quartile_all_w15_49_who_are_anaemic_pct) AS all_w15_49_who_are_anaemic_pct,
    (m15_plus_who_use_any_kind_of_tobacco_pct, rank_m15_plus_who_use_any_kind_of_tobacco_pct, quartile_m15_plus_who_use_any_kind_of_tobacco_pct) AS m15_plus_who_use_any_kind_of_tobacco_pct
  ))
),
indicators AS (
  SELECT collect_list(CASE WHEN m.indicator_column IS NOT NULL THEN named_struct(
           'indicator_column', m.indicator_column, 'label', m.label_for_users, 'value', l.value,
           'unit', m.unit, 'rank_of_706', l.rank_of_706, 'quartile', l.quartile,
           'direction', m.direction, 'reason', m.reason) END) AS indicators,
         max(CASE WHEN m.indicator_column IS NULL THEN m.reason END) AS no_indicator_reason,
         count(m.service) AS n_map_rows
  FROM workspace.vf.service_indicator_map m
  JOIN params p ON m.service = p.service
  LEFT JOIN long l ON l.indicator_column = m.indicator_column
),
district_fac AS (
  SELECT fd.unique_id
  FROM workspace.vf.facility_district fd JOIN chosen c
    ON (c.nfhs_key IS NOT NULL AND fd.nfhs_key = c.nfhs_key) OR (c.nfhs_key IS NULL AND fd.pin_key = c.pin_key)
),
district_counts AS (
  SELECT count(*) AS n_facilities_in_district,
         count_if(fs.tier = 'Confirmed') AS n_confirmed_in_district,
         count_if(fs.tier = 'Likely') AS n_likely_in_district,
         count_if(fs.tier = 'Possible') AS n_possible_in_district
  FROM district_fac df
  LEFT JOIN workspace.vf.facility_service fs
    ON fs.unique_id = df.unique_id AND fs.service = (SELECT service FROM params)
),
confirmed AS (
  SELECT fs.unique_id, fc.name, fl.location_source, fl.location_confidence,
         fl.location_source = 'coordinates' AND fl.location_confidence IN ('high', 'good') AS exact_coords,
         workspace.vf.haversine_km(pt.lat, pt.lon, fl.final_lat, fl.final_lon) AS km
  FROM workspace.vf.facility_service fs
  JOIN params p ON fs.service = p.service
  JOIN workspace.vf.facilities_clean fc ON fc.unique_id = fs.unique_id AND NOT fc.is_shifted
  JOIN workspace.vf.facility_location fl ON fl.facility_id = fs.unique_id
  CROSS JOIN point pt
  WHERE fs.tier = 'Confirmed' AND fl.final_lat IS NOT NULL AND pt.lat IS NOT NULL
),
nearest_exact AS (
  SELECT named_struct('unique_id', unique_id, 'name', name, 'km', round(km, 1),
                      'location_source', location_source, 'location_confidence', location_confidence) AS s
  FROM confirmed WHERE exact_coords ORDER BY km LIMIT 1
),
nearest_any AS (
  SELECT named_struct('unique_id', unique_id, 'name', name, 'km', round(km, 1),
                      'location_source', location_source, 'location_confidence', location_confidence) AS s
  FROM confirmed ORDER BY km LIMIT 1
)
SELECT p.service, p.pin AS pin_given,
       c.district, c.state, c.pin AS district_from_pin, c.pin_share, c.district_method,
       round(c.pin_centre_km, 2) AS pin_centre_km,
       c.nfhs_key, c.match_method AS nfhs_match_method, al.note AS alias_note,
       n.district AS nfhs_district, n.state AS nfhs_state,
       pt.lat AS point_lat, pt.lon AS point_lon, pt.point_source,
       i.indicators, i.no_indicator_reason, i.n_map_rows,
       dc.n_facilities_in_district, dc.n_confirmed_in_district, dc.n_likely_in_district, dc.n_possible_in_district,
       (SELECT s FROM nearest_exact) AS nearest_confirmed_exact,
       (SELECT s FROM nearest_any) AS nearest_confirmed_any,
       'NFHS-5, 2019-21' AS nfhs_source
FROM params p
CROSS JOIN point pt
LEFT JOIN chosen c ON TRUE
LEFT JOIN nfhs n ON TRUE
LEFT JOIN workspace.vf.district_alias al ON c.match_method = 'alias' AND al.pin_key = c.pin_key
CROSS JOIN indicators i
CROSS JOIN district_counts dc

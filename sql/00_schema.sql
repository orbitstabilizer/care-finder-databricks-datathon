-- Target schema and the distance function every other file uses.
CREATE SCHEMA IF NOT EXISTS {TGT};

CREATE OR REPLACE FUNCTION {F_HAVERSINE}(
  lat1 DOUBLE, lon1 DOUBLE, lat2 DOUBLE, lon2 DOUBLE
) RETURNS DOUBLE
COMMENT 'Great-circle distance in km between two WGS84 points.'
RETURN 6371.0088 * 2 * asin(sqrt(
    pow(sin(radians(lat2 - lat1) / 2), 2)
  + cos(radians(lat1)) * cos(radians(lat2)) * pow(sin(radians(lon2 - lon1) / 2), 2)
));

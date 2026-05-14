-- =============================================================
-- 26_raw_weather.sql
-- RAW Weather data tables (NOAA)
-- Source: https://api.weather.gov
-- Schema: raw
-- Tables: raw.weather_stations, raw.weather_forecasts, raw.weather_periods
-- NOTE:   All fields from the NOAA API endpoints
--         are preserved here exactly as returned.
-- =============================================================

-- -----------------------------------------------------------
-- raw.weather_stations
-- Station metadata from points endpoint
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.weather_stations (
    id                    TEXT         NOT NULL PRIMARY KEY,
    elevation             TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- raw.weather_forecasts
-- Forecast data from forecast endpoint
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.weather_forecasts (
    id                    TEXT         NOT NULL PRIMARY KEY,
    station_id            TEXT         REFERENCES raw.weather_stations(id),
    updated               TIMESTAMPTZ,
    units                 TEXT,
    forecast_generated_at TIMESTAMPTZ,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_weather_forecasts_station_id ON raw.weather_forecasts (station_id);
CREATE INDEX IF NOT EXISTS ix_weather_forecasts_updated ON raw.weather_forecasts (updated);

-- -----------------------------------------------------------
-- raw.weather_periods
-- Individual forecast periods from forecast endpoint
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.weather_periods (
    id                    TEXT         NOT NULL PRIMARY KEY,
    forecast_id           TEXT         NOT NULL REFERENCES raw.weather_forecasts(id),
    number                INTEGER,
    name                  TEXT,
    start_time            TIMESTAMPTZ,
    end_time              TIMESTAMPTZ,
    is_daytime            BOOLEAN,
    temperature           INTEGER,
    temperature_unit      TEXT,
    temperature_trend     TEXT,
    wind_speed            TEXT,
    wind_direction        TEXT,
    icon                  TEXT,
    short_forecast        TEXT,
    detailed_forecast     TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_weather_periods_forecast_id ON raw.weather_periods (forecast_id);
CREATE INDEX IF NOT EXISTS ix_weather_periods_start_time ON raw.weather_periods (start_time);
CREATE INDEX IF NOT EXISTS ix_weather_periods_name ON raw.weather_periods (name);
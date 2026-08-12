-- Retrosheet's TEAMABR reference intentionally focuses on affiliated major
-- leagues.  TEAM{year}.TXT, landed as raw.retrosheet_team0, supplies official
-- date-bounded identity records for its additional historical teams, including
-- Negro Leagues and the 2025 Athletics code.  Use it only for codes absent
-- from TEAMABR; it is an authoritative supplement, not a name-match override.
INSERT INTO core.team (retro_team_id, league, city, nickname, first_year, last_year)
SELECT
    supplemental.team,
    NULL,
    supplemental.city,
    supplemental.nickname,
    substring(supplemental.first_g FROM 1 FOR 4)::integer,
    substring(supplemental.last_g FROM 1 FOR 4)::integer
FROM raw.retrosheet_team0 supplemental
WHERE supplemental.first_g ~ '^[0-9]{8}$'
  AND supplemental.last_g ~ '^[0-9]{8}$'
  AND NOT EXISTS (
      SELECT 1
      FROM raw.retrosheet_team primary_reference
      WHERE primary_reference.team_id = supplemental.team
  );

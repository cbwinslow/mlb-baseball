# MLB Stats API endpoint inventory

Probed 2026-10-07 against `https://statsapi.mlb.com` (one GET per path, sample ids, read-only). The path list comes from the community OpenAPI file (see `docs/SOURCE_RIGHTS.md`); the probe result is what the live API returned. Families and fields are described in [`mlb_api.md`](mlb_api.md); this page is the per-path checklist.

Status: `held` = the `mlb_api` connector loads it; `wanted` = analytical data worth a rights check, cost estimate and ingest (owned by `full-source-ingestion`); `scope` = cosmetic, media, event ephemera or internal, recorded and not wanted; `unavailable` = the live probe failed (reason given). `wanted` and `scope` are proposals the owner can change.

Totals: 190 paths. held 20, scope 18, unavailable 37, wanted 115.

| Path | Probe | Status | Reason |
|---|---|---|---|
| `/achievementStatuses` | 200 | wanted | reference catalog |
| `/analytics/game` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/analytics/guids` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/attendance` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/awards` | 200 | held | loaded by `mlb_api` connector |
| `/awards/{awardId}` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/awards/{awardId}/recipients` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/baseballStats` | 200 | wanted | reference catalog |
| `/batTracking/game/{gamePk}/{playId}` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/broadcast` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/broadcastAvailability` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/broadcasters` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/coachingVideoTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/conferences` | 200 | wanted | reference catalog |
| `/conferences/{conferenceId}` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/divisions` | 200 | held | loaded by `mlb_api` connector |
| `/divisions/{divisionId}` | 200 | wanted | reference catalog |
| `/draft` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/draft/prospects` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/draft/prospects/{year}` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/draft/{year}` | 200 | held | loaded by `mlb_api` connector |
| `/draft/{year}/latest` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/eventStatus` | 200 | wanted | reference catalog |
| `/eventTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/fielderDetailTypes` | 200 | wanted | reference catalog |
| `/freeGameTypes` | 200 | wanted | reference catalog |
| `/game/changes` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/game/lastPitch` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/game/{gamePk}/contextMetrics` | 200 | held | loaded by `mlb_api` connector |
| `/game/{gamePk}/guids` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/game/{gamePk}/winProbability` | 200 | held | loaded by `mlb_api` connector |
| `/game/{gamePk}/withMetrics` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/game/{gamePk}/{guid}/analytics` | unprobed | wanted | ; needs a sample value |
| `/game/{gamePk}/{guid}/contextMetrics` | unprobed | wanted | ; needs a sample value |
| `/game/{gamePk}/{guid}/contextMetricsAverages` | unprobed | wanted | ; needs a sample value |
| `/game/{gamePk}/{guid}/homeRunBallparks` | unprobed | wanted | ; needs a sample value |
| `/game/{gamePk}/{playId}/analytics/biomechanics/{positionId}` | unprobed | wanted | ; needs a sample value |
| `/game/{gamePk}/{playId}/analytics/skeletalData/chunked` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/game/{gamePk}/{playId}/analytics/skeletalData/files` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/game/{game_pk}/boxscore` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/game/{game_pk}/content` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/game/{game_pk}/feed/color` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/game/{game_pk}/feed/color/timestamps` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/game/{game_pk}/feed/live` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/game/{game_pk}/feed/live/diffPatch` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/game/{game_pk}/feed/live/timestamps` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/game/{game_pk}/linescore` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/game/{game_pk}/playByPlay` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/gamePace` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/gameStatus` | 200 | wanted | reference catalog |
| `/gameTypes` | 200 | held | loaded by `mlb_api` connector |
| `/gamedayTypes` | 200 | wanted | reference catalog |
| `/groupByTypes` | 200 | wanted | reference catalog |
| `/highLow/types` | 200 | wanted | reference catalog |
| `/highLow/{highLowType}` | unprobed | wanted | ; needs a sample value |
| `/hitTrajectories` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/homeRunDerby` | 500 | unavailable | 500 from the source |
| `/homeRunDerby/bracket` | 500 | unavailable | 500 from the source |
| `/homeRunDerby/mixed` | 500 | unavailable | 500 from the source |
| `/homeRunDerby/pool` | 500 | unavailable | 500 from the source |
| `/homeRunDerby/{gamePk}` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/homeRunDerby/{gamePk}/bracket` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/homeRunDerby/{gamePk}/mixed` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/homeRunDerby/{gamePk}/pool` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/jobTypes` | 200 | wanted | reference catalog |
| `/jobs` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/jobs/datacasters` | 200 | held | loaded by `mlb_api` connector |
| `/jobs/officialScorers` | 200 | held | loaded by `mlb_api` connector |
| `/jobs/umpires` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/jobs/umpires/games/{umpireId}` | unprobed | wanted | ; needs a sample value |
| `/languages` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/league` | 200 | wanted | reference catalog |
| `/league/allStarBallot` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/league/{leagueId}` | 200 | wanted | reference catalog |
| `/league/{leagueId}/allStarBallot` | 200 | wanted | reference catalog |
| `/league/{leagueId}/allStarFinalVote` | 200 | wanted | reference catalog |
| `/league/{leagueId}/allStarWriteIns` | 200 | wanted | reference catalog |
| `/leagueLeaderTypes` | 200 | wanted | reference catalog |
| `/leagues` | 200 | held | loaded by `mlb_api` connector |
| `/leagues/allStarBallot` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/leagues/{leagueId}` | 200 | wanted | reference catalog |
| `/leagues/{leagueId}/allStarBallot` | 200 | wanted | reference catalog |
| `/leagues/{leagueId}/allStarFinalVote` | 200 | wanted | reference catalog |
| `/leagues/{leagueId}/allStarWriteIns` | 200 | wanted | reference catalog |
| `/logicalEvents` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/lookup/values/all` | 200 | wanted | reference catalog |
| `/mediaState` | 200 | wanted | reference catalog |
| `/metrics` | 200 | wanted | reference catalog |
| `/milestoneDurations` | 200 | wanted | reference catalog |
| `/milestoneLookups` | 200 | wanted | reference catalog |
| `/milestoneStatistics` | 200 | wanted | reference catalog |
| `/milestoneTypes` | 200 | wanted | reference catalog |
| `/milestones` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/moundVisitTypes` | 200 | wanted | reference catalog |
| `/people` | 400 | held | 400 without full parameters; needs a parameterised probe |
| `/people/changes` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/people/freeAgents` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/people/search` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/people/{personId}` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/people/{personId}/awards` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/people/{personId}/stats` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/people/{personId}/stats/game/{gamePk}` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/people/{personId}/stats/metrics` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/performerTypes` | 200 | wanted | reference catalog |
| `/pitchCodes` | 200 | wanted | reference catalog |
| `/pitchTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/platforms` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/playerStatusCodes` | 200 | wanted | reference catalog |
| `/positions` | 200 | held | loaded by `mlb_api` connector |
| `/props/play/predictions` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/props/play/predictions/adjust` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/review` | 500 | unavailable | 500 from the source |
| `/reviewReasons` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/roofTypes` | 200 | wanted | reference catalog |
| `/rosterTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/ruleSettings` | 200 | wanted | reference catalog |
| `/runnerDetailTypes` | 200 | wanted | reference catalog |
| `/schedule` | 400 | held | 400 without full parameters; needs a parameterised probe |
| `/schedule/games/tied` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/schedule/postseason` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/schedule/postseason/series` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/schedule/postseason/tuneIn` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/schedule/trackingEvents` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/schedule/{scheduleType}` | unprobed | wanted | ; needs a sample value |
| `/scheduleEventTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/scheduleTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/seasons` | 400 | held | 400 without full parameters; needs a parameterised probe |
| `/seasons/all` | 200 | wanted | reference catalog |
| `/seasons/{seasonId}` | unprobed | wanted | ; needs a sample value |
| `/situationCodes` | 200 | wanted | reference catalog |
| `/sky` | 200 | wanted | reference catalog |
| `/sortModifiers` | 200 | wanted | reference catalog |
| `/sports` | 200 | held | loaded by `mlb_api` connector |
| `/sports/{sportId}` | 200 | wanted | reference catalog |
| `/sports/{sportId}/allSportBallot` | 200 | wanted | reference catalog |
| `/sports/{sportId}/players` | 200 | wanted | reference catalog |
| `/standings` | 200 | held | loaded by `mlb_api` connector |
| `/standings/{standingsType}` | unprobed | wanted | ; needs a sample value |
| `/standingsTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/statFields` | 200 | wanted | reference catalog |
| `/statGroups` | 200 | wanted | reference catalog |
| `/statTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/statcastPositionTypes` | 200 | wanted | reference catalog |
| `/stats` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/stats/analytics/outsAboveAverage` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/stats/analytics/sprayChart` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/stats/analytics/stolenBaseProbability` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/stats/grouped` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/stats/leaders` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/stats/metrics` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/stats/search` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/stats/search/config` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/stats/search/groupByTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/stats/search/params` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/stats/search/stats` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/streaks` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/streaks/types` | 200 | wanted | reference catalog |
| `/teams` | 200 | held | loaded by `mlb_api` connector |
| `/teams/affiliates` | 400 | wanted | 400 without full parameters; needs a parameterised probe |
| `/teams/history` | 404 | held | loaded by `mlb_api` connector |
| `/teams/stats` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/stats/leaders` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}/affiliates` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}/alumni` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}/coaches` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}/history` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}/leaders` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/teams/{teamId}/personnel` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/teams/{teamId}/roster` | 200 | held | loaded by `mlb_api` connector |
| `/teams/{teamId}/roster/{rosterType}` | unprobed | wanted | ; needs a sample value |
| `/teams/{teamId}/stats` | 404 | unavailable | 404 with sample ids; may need other parameters |
| `/trackingSoftwareVersions` | 200 | wanted | reference catalog |
| `/trackingSystemOwners` | 200 | wanted | reference catalog |
| `/trackingVendors` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/trackingVersions` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/transactionTypes` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/transactions` | 400 | held | 400 without full parameters; needs a parameterised probe |
| `/uniforms/game` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/uniforms/team` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/venues` | 200 | held | loaded by `mlb_api` connector |
| `/venues/{venueId}` | 200 | wanted | analytical data; needs rights check and cost estimate before ingest |
| `/videoResolutionTypes` | 200 | scope | cosmetic, media, event ephemera or internal |
| `/violationTypes` | 200 | wanted | reference catalog |
| `/weather/game/{gamePk}/forecast/{roofType}` | unprobed | wanted | ; needs a sample value |
| `/weather/game/{gamePk}/{playId}` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/weather/venues/{venueId}/basic` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/weather/venues/{venueId}/full` | 401 | unavailable | 401: needs MLB authorization we do not hold |
| `/weatherTrajectoryConfidences` | err | unavailable | connection reset on probe |
| `/windDirection` | 200 | wanted | reference catalog |

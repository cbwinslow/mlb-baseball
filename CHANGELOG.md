# Changelog
All notable changes to this project will be documented in this file.

## [v0.1.0] - 2026-05-14
### Added
- Complete raw data ingestion capability for 7 data sources:
  * MLB StatsAPI (schedule, game data, standings, rosters)
  * Retrosheet (event files, game logs, rosters)
  * StatCast (pitch-by-pitch data)
  * FanGraphs (batting, pitching, fielding statistics)
  * Lahman (complete historical database)
  * ESPN (scoreboard, events, competitions, venues, broadcasts)
  * Weather (NOAA forecast data, stations, forecast periods)
- Standardized ingestor interface with dry-run support
- Batch processing with PostgreSQL UPSERT for idempotent operations
- Comprehensive test suite for all ingestors
- CLI commands for each source: `baseball ingest <source> [options]`
- Source registry for easy extension
- GitHub workflow setup with branching strategy, issue templates, PR templates, and CI/CD
- Documentation including CONTRIBUTING.md and this CHANGELOG

### Fixed
- MLB StatsAPI ingestor was writing to core tables instead of raw tables
- Various test fixes for existing ingestors (MLB, Retrosheet, StatCast)

### Changed
- Updated source registry to include all new sources
- Enhanced CLI ingest commands with new source options
- Improved error handling and logging across all sources
- Updated AGENTS.md to include GitHub workflow guidelines

### Removed
- None

## [Unreleased]
### Added
- Feature engineering layer (planned for v0.2.0)
- Model training and registration (planned for v0.3.0)
- Prediction workflows (planned for v0.4.0)
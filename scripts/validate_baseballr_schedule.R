#!/usr/bin/env Rscript

# Optional independent schedule reference for the conformance rehearsal.
# This script is never called by bootstrap, ingestion, conformance, or pytest.
# It requires a user-installed R + baseballr and writes only a local CSV.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("usage: Rscript scripts/validate_baseballr_schedule.R YYYY-MM-DD output.csv")
}
if (!requireNamespace("baseballr", quietly = TRUE)) {
  stop("optional validation requires R package 'baseballr'; it is not a project dependency")
}

games <- baseballr::mlb_game_pks(args[[1]], level_ids = 1)
wanted <- c(
  "game_pk", "gameGuid", "game_guid", "officialDate", "official_date",
  "gameNumber", "game_number", "doubleHeader", "double_header",
  "away_name", "home_name", "away_team_name", "home_team_name"
)
available <- intersect(wanted, names(games))
utils::write.csv(games[, available, drop = FALSE], args[[2]], row.names = FALSE)
message("wrote optional baseballr reference: ", args[[2]])

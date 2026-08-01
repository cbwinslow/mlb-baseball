-- core.play_old/core.pitch_old are inert leftovers from migration 0011's
-- season-partitioning of core.play/core.pitch -- renamed off to the side as
-- a rollback snapshot, FK constraints already dropped there, never read by
-- any code since (confirmed: no reference anywhere in mlb_baseball/ or
-- migrations/ outside 0011 itself). ~6.2GB combined (16.5M + 13.4M rows),
-- pure disk/cache/vacuum overhead for data nothing uses. Migration 0011
-- shipped and has been running in production for a while -- if a rollback
-- were still needed, it would have happened by now.
DROP TABLE core.play_old;
DROP TABLE core.pitch_old;

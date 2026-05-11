-- 10_extensions/03_btree_gin.sql
-- Enable btree_gin so GIN indexes can include btree-comparable columns
-- (e.g. season integer inside a composite GIN index).

CREATE EXTENSION IF NOT EXISTS btree_gin;

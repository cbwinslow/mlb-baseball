-- 10_extensions/01_uuid.sql
-- Enable the pgcrypto and uuid-ossp extensions required for UUID primary keys.
-- Safe to run multiple times (IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

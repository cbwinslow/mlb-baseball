# Operational Milestone: System Administration & Database Performance Optimization

**Date:** 2026-10-05
**Host:** `cbwdellr720` (Dell PowerEdge R720, 40 Cores, 128 GB RAM, Software RAID5 `md0`)
**Target Databases:** PostgreSQL 16 (`mlb`, port 5432), PostgreSQL 17 (`opendiscourse`, port 5434)

---

## 1. Executive Summary

A comprehensive performance, system administration, and database optimization pass was executed to eliminate disk saturation (I/O wait previously causing database lockups and severe query stalls), prune energy/CPU hogs, optimize network interfaces, and remediate critical indexing gaps across high-volume Retrosheet and metadata tables.

Key results:
- **Disk I/O Wait:** Dropped from persistent high double-digits to **~2.0%**.
- **CPU Idle:** Stabilized at **~74% idle** (down from spinning runaway processes).
- **Physical Drive %util:** RAID5 component drives (`sda`, `sdb`, `sdc`, `sdd`, `sdf`) dropped to **8%–12% %util** under active ingestion.
- **Query Latencies:** Lookups on `raw.retrosheet_plays` dropped from 45–50-second full sequential scans (20 GB table) to **<1 ms index scans**.

---

## 2. System Administration & Daemon Pruning

1. **RabbitMQ Decommissioning:**
   - Stopped and disabled `rabbitmq-server.service`, `epmd.service`, and `epmd.socket`.
   - Verified no active application code in `mlb` or `opendiscourse` depended on RabbitMQ.
2. **CrowdSec / Fail2ban Modernization:**
   - Installed `crowdsec-firewall-bouncer-nftables` and registered with local API.
   - Bound directly to kernel `nftables` hooks (`crowdsec-blacklists-CAPI` dropping malicious traffic at priority filter - 10).
   - Stopped and disabled `fail2ban.service`.
   - Refactored `service_monitor.sh` to remove legacy fail2ban scrape loops.
3. **Runaway Daemon Retirement:**
   - Stopped and disabled `clickhouse-server.service` (duplicate unused installation) and `clamav-daemon.service`.
   - Reclaimed ~3 GB of resident RAM and 100% of a pegged CPU core. Pruned ClickHouse scrape target from Prometheus configuration.
4. **Service Quarantine & Tool Shutdown:**
   - Decommissioned idle containers (Langfuse, Datahub, Surfsense) and cleaned up unused database stubs while safeguarding production PostgreSQL bare-metal instances on ports 5432 and 5434.

---

## 3. Network, Kernel & Storage Tuning

1. **Samba 10G Reconfiguration:**
   - Reconfigured `/etc/samba/smb.conf` to bind strictly to localhost, 10G direct interface `eno2` (`192.168.10.1`), and local subnet `192.168.4.101/22`.
   - Restricted access to trusted subnets: `127.0.0.1`, `192.168.10.0/24`, `192.168.4.0/22`.
   - Validated configuration with `testparm -s` and restarted `smbd` / `nmbd`.
2. **Software RAID5 Optimization:**
   - Increased `stripe_cache_size` on `/sys/block/md0/md/stripe_cache_size` from 256 to 4096.
   - Made persistent across reboots via `/etc/udev/rules.d/60-md-stripe-cache.rules`.
3. **Filesystem Mounts (`noatime`):**
   - Added `noatime` mount option to `/` in `/etc/fstab` and remounted live (`mount -o remount,noatime /`).
   - Drastically cut rotational seek penalties and write amplification on file reads.
4. **PostgreSQL WAL & HugePages Configuration:**
   - Tuned `min_wal_size = '4GB'` on PostgreSQL 16 via `ALTER SYSTEM` and reloaded configuration.
   - Configured `vm.nr_hugepages = 21500` in `/etc/sysctl.d/60-hugepages.conf` and `/etc/sysctl.conf` to reserve 42 GB of 2 MB HugePages upon clean boot.
5. **Internal Monitoring Refactoring (`sys_mon`):**
   - Refactored all 14 `sys_mon` metrics collection scripts to use single-pass stream processing.
   - Total cron execution sweep time plummeted from **85 seconds to 1.9 seconds**.
   - Pruned duplicate crontab disk and network loggers; cleaned rotated logs older than 30 days (freed 1.4 GB).

---

## 4. Database Indexing & Retrosheet Remediation (Completed)

All index operations were executed using `CREATE INDEX CONCURRENTLY` or `DROP INDEX CONCURRENTLY` after verifying zero active transactions or table locks. Active background processes (including the nightly pipeline and Polymarket backfill) were unaffected.

### A. Duplicate Indexes Dropped Concurrently (Reclaimed ~348 MB)
1. `raw.retrosheet_plays.retrosheet_plays__season_idx` (240 MB)
2. `raw.retrosheet_batting.retrosheet_batting__season_idx` (84 MB)
3. `core.game.game_game_pk_idx` (9.2 MB - redundant with unique key `core_game_game_pk_key`)
4. `raw.retrosheet_teamstats.retrosheet_teamstats__season_idx` (7.7 MB)
5. `raw.retrosheet_gamelog.retrosheet_gamelog__season_idx` (3.7 MB)
6. `raw.retrosheet_gameinfo.retrosheet_gameinfo__season_idx` (3.5 MB)

### B. High-Impact Indexes Created Concurrently & Verified Valid (`indisvalid = true`)
1. **`raw.retrosheet_plays`**: `idx_retrosheet_plays_gid` on `(gid)` (16.9M rows, 115 MB). Single-game lookups dropped from ~45-50s full-table scans to <1ms index scans.
2. **`raw.retrosheet_event`**: `idx_retrosheet_event_game_event` on `(game_id, event_id)` (16.7M rows, 501 MB).
3. **`raw.retrosheet_game`**: `idx_retrosheet_game_game_id` on `(game_id)` (210k rows, 6.7 MB). Eliminates 2.39 billion sequential reads across 12,859 scans.
4. **`raw.retrosheet_box_batting`**: `idx_retrosheet_box_batting_game_id` on `(game_id)` (353k rows, 3.0 MB). Eliminates 1.28 billion sequential reads across 5,379 scans.
5. **`raw.fangraphs_projection`**: `idx_fangraphs_projection_playerid` on `(playerid)` (240 MB table, 3.5 MB index). Replaces unindexed table scans.
6. **`raw.mlb_transaction`**: `idx_mlb_transaction_person_id` on `(person_id)` (159k rows, 8.2 MB). Eliminates 290 million sequential reads on player transaction history.
7. **`raw.retrosheet_pitching`**: `idx_retrosheet_pitching_gid` on `(gid)` (2.4M rows, 16 MB).
8. **`raw.retrosheet_batting`**: `idx_retrosheet_batting_gid` on `(gid)` (5.1M rows, 44 MB). Eliminates the single largest sequential scan culprit in the database (**17.6 billion** sequential tuples read across 3,932 scans).
9. **`raw.retrosheet_fielding`**: `idx_retrosheet_fielding_gid` on `(gid)` (5.26M rows, 41 MB).

---

## 5. Deferred Optimization Items

1. **`meta.ingestion_item (run_id)`**:
   - `ingestion_item_run_id_fkey` lacks a supporting index on `run_id`.
   - Deferred while background Kalshi operations hold open transaction locks on `meta.ingestion_item`.
2. **`raw.polymarket_price (clob_token_id, ts)`**:
   - 94 GB table currently only indexed on `(clob_token_id)`.
   - Deferred until the ongoing historical backfill (`PID 1796135`) completes.

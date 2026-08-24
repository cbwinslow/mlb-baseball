"""`mlb doctor` — one command to check whether everything is actually working.
See CLAUDE.md "Operational health checks": every connector is expected to
contribute its own checks via health_check(), not be invisible until it
breaks.

Every check here is defensive against a database that's reachable but
otherwise not yet set up (no schemas, no migrations applied) — that's not a
hypothetical: it's exactly the state a brand-new clone's database is in
before the first `mlb migrate`, and doctor crashing with a raw traceback
right there is the worst possible first impression. Detail messages name the
actual next command to run (`mlb migrate`, `mlb ingest <source> --mode
bootstrap`) wherever there's an obvious one, not just "X is wrong" — the
point is to make doctor's output something a person (or an agent) can act on
directly, not just a status light.
"""

import psycopg

from mlb_baseball import (
    api,
    backup,
    conform,
    daemon,
    dump,
    ingest,
    manifest,
    migrate,
    model,
    pipeline,
    report,
    visual,
)
from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check, check_never_vacuumed
from mlb_baseball.model import experiment, feature_select_stepwise
from mlb_baseball.registry import CONNECTORS


def _database_reachable() -> Check:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return Check("database reachable", True, "connected via DATABASE_URL")
    except Exception as exc:
        return Check(
            "database reachable",
            False,
            f"{exc} — check DATABASE_URL in .env points at a running Postgres instance",
        )


_REQUIRED_SCHEMAS = {"raw", "core", "gold", "meta"}


def _required_schemas_exist() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)",
                (list(_REQUIRED_SCHEMAS),),
            )
            found = {row[0] for row in cur.fetchall()}
    missing = _REQUIRED_SCHEMAS - found
    if missing:
        return Check(
            "required schemas",
            False,
            f"missing: {', '.join(sorted(missing))} — run `mlb migrate`",
        )
    return Check("required schemas", True, f"{', '.join(sorted(_REQUIRED_SCHEMAS))} all present")


def _migrations_up_to_date() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT version FROM public.schema_migrations")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check("migrations", False, "no migrations applied yet — run `mlb migrate`")
            applied = {row[0] for row in cur.fetchall()}
    all_migrations = {p.name for p in migrate.MIGRATIONS_DIR.glob("*.sql")}
    pending = all_migrations - applied
    if pending:
        return Check(
            "migrations",
            False,
            f"pending: {', '.join(sorted(pending))} — run `mlb migrate`",
        )
    return Check("migrations", True, f"{len(applied)} applied, none pending")


def _downloads_directory_ok() -> Check:
    ok, detail = manifest.check_downloads_directory()
    return Check("downloads directory", ok, detail)


def _pg_stat_statements_enabled() -> Check:
    """Confirms pg_stat_statements is actually installed and tracking, not
    just present in pg_available_extensions — it requires being loaded via
    shared_preload_libraries (a server restart, not a plain CREATE
    EXTENSION), so a `CREATE EXTENSION IF NOT EXISTS` here could silently
    "succeed" while the extension still isn't actually recording anything.
    This is what makes real query-timing investigations possible at all
    (see docs/DECISIONS.md ADR-043) — flagging it here means a missing
    monitoring precondition shows up in `mlb doctor`, not only when someone
    goes looking for it mid-investigation."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'")
            if cur.fetchone() is None:
                return Check(
                    "pg_stat_statements",
                    False,
                    "not installed — run `CREATE EXTENSION pg_stat_statements` "
                    "(requires it in shared_preload_libraries first, server restart needed)",
                )
            cur.execute("SELECT count(*) FROM pg_stat_statements")
            (count,) = fetch_one(cur)
    return Check("pg_stat_statements", True, f"tracking {count} distinct statements")


def _stale_ingestion_runs() -> Check:
    """Report stale runs without changing operational state.

    ``mlb doctor`` is deliberately safe to run in monitoring and CI.  An
    owner can explicitly repair these rows with ``mlb repair-runs``.
    """
    with get_connection() as conn:
        try:
            stale = ingest.stale_runs(conn)
        except psycopg.errors.UndefinedTable:
            conn.rollback()
            return Check(
                "stale ingestion runs",
                True,
                "meta.ingestion_run doesn't exist yet — nothing to check",
            )
    if not stale:
        return Check("stale ingestion runs", True, "none found")
    names = ", ".join(f"{r['source']} ({r['mode']}, pid {r['pid']})" for r in stale)
    return Check(
        "stale ingestion runs", False, f"{len(stale)} found: {names} — run `mlb repair-runs`"
    )


def _workflow_lock_state() -> Check:
    """Expose a live workflow conflict without changing its owner or state.

    A single-bigint pg_advisory_lock/pg_advisory_lock_shared's key is split
    across pg_locks.classid (high 32 bits) and .objid (low 32 bits),
    objsubid=1 marking this form -- matching only on objid could in
    principle match a different advisory lock sharing the same low 32
    bits. Verified directly against a real held lock: reconstructing
    (classid << 32 | objid) reproduces hashtext(key)::bigint exactly,
    including the negative-hashtext case a key like this one can produce.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.pid, a.state
            FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory'
              AND l.objsubid = 1
              AND (l.classid::bigint << 32) | l.objid::bigint
                  = hashtext('mlb-workflow:raw-core-model')::bigint
              AND l.granted AND a.pid <> pg_backend_pid()
            ORDER BY a.pid
            """
        )
        holders = cur.fetchall()
    if not holders:
        return Check("workflow lock", True, "no active raw/core/model workflow")
    details = ", ".join(f"pid {pid} ({state})" for pid, state in holders)
    return Check(
        "workflow lock",
        False,
        f"active workflow lock held by {details} — wait for it to finish; "
        "do not start ingest/conform/model",
    )


# (name, check_fn) — every entry runs independently and defensively: a bug or
# an unexpected DB state in any one check must never prevent the rest from
# reporting, since that's exactly the "doctor itself is broken" failure mode
# this command exists to avoid for every *other* part of the system.
_CORE_CHECKS = [
    ("required schemas", _required_schemas_exist),
    ("migrations", _migrations_up_to_date),
    ("downloads directory", _downloads_directory_ok),
    ("pg_stat_statements", _pg_stat_statements_enabled),
    ("stale ingestion runs", _stale_ingestion_runs),
    ("workflow lock", _workflow_lock_state),
    ("never-vacuumed tables", check_never_vacuumed),
]


def run() -> list[Check]:
    db_check = _database_reachable()
    if not db_check.ok:
        return [db_check]  # nothing else can run without a DB connection

    checks = [db_check]
    for name, check_fn in _CORE_CHECKS:
        try:
            checks.append(check_fn())
        except Exception as exc:
            checks.append(Check(name, False, f"check raised: {exc}"))

    for name, connector in CONNECTORS.items():
        health_check = getattr(connector, "health_check", None)
        if health_check is None:
            checks.append(Check(f"{name} connector", False, "no health_check() defined"))
            continue
        try:
            checks.extend(health_check())
        except Exception as exc:
            # One connector's health_check() blowing up (e.g. querying a table
            # that's never been bootstrapped) shouldn't blind doctor to every
            # other connector's health — report it as a failed check instead.
            checks.append(Check(f"{name} connector", False, f"health_check() raised: {exc}"))

    # conform.py isn't in CONNECTORS — it has no bootstrap()/update() (it
    # transforms already-ingested raw data rather than fetching from a
    # source), so it's checked here directly instead of through the
    # connector loop above.
    try:
        checks.extend(conform.health_check())
    except Exception as exc:
        checks.append(Check("core connector", False, f"health_check() raised: {exc}"))

    # Same reasoning as conform.py above -- model has no bootstrap()/
    # update(), it's not in CONNECTORS.
    try:
        checks.extend(model.health_check())
    except Exception as exc:
        checks.append(Check("model", False, f"health_check() raised: {exc}"))

    # Reporting is a separate derived stage, like conformance and model
    # building rather than a network connector.  It must be visible in the
    # one-command operational picture too.
    try:
        checks.extend(report.health_check())
    except Exception as exc:
        checks.append(Check("report", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(experiment.health_check())
    except Exception as exc:
        checks.append(Check("experiment", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(feature_select_stepwise.health_check())
    except Exception as exc:
        checks.append(Check("feature_select_stepwise", False, f"health_check() raised: {exc}"))

    from mlb_baseball import serve
    from mlb_baseball.model import (
        active_spin,
        aging,
        air_trap,
        ambush,
        arm,
        arm_accuracy,
        arm_align,
        arm_slot,
        babip,
        backtest,
        baserunning,
        blast_angle,
        block_suppress,
        blocking,
        bullpen,
        bullpen_opt,
        bunt,
        bunt_charge,
        bvp,
        calibration,
        carry,
        catch_prob,
        catch_xchg,
        catcher_pop,
        chase_recog,
        cluster,
        clutch,
        contact_depth,
        count,
        damage,
        decision,
        diversity,
        dp_footwork,
        drift,
        entropy,
        exp_resist,
        ext_perceive,
        extension,
        fatigue,
        fatigue_drop,
        first_pitch_ambush,
        first_step,
        foul_attrition,
        fstrike,
        gyro_spin,
        haa,
        heat_check,
        heatmap,
        hedge,
        high_heat,
        iffb,
        intent_leak,
        lead_snap,
        leverage,
        low_scoop,
        neural,
        nrfi,
        oppo_gap,
        outfield_target,
        parlay,
        pivot_dp,
        poptime,
        portfolio,
        props,
        pull_air,
        pull_barrel,
        pull_gb,
        pull_slice,
        putaway,
        putaway_depth,
        putaway_exec,
        rel_drift,
        reliever,
        ros,
        route_burst,
        season,
        shift,
        shop,
        simulate,
        slash_oppo,
        spin,
        spin_align,
        splits,
        spray,
        ssw,
        ssw_latent,
        stack,
        stuff,
        sub,
        sweetspot,
        travel,
        tto,
        tunnel,
        two_strike,
        umpire,
        vaa,
        vaa_toz,
        velo_delta,
        velo_drift,
        wall,
        wall_block,
        wall_crash,
        weather,
        wpa,
        xslg,
        zone_swing,
        zone_whiff,
    )

    try:
        checks.extend(serve.health_check())
    except Exception as exc:
        checks.append(Check("serve", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(simulate.health_check())
    except Exception as exc:
        checks.append(Check("simulate", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(props.health_check())
    except Exception as exc:
        checks.append(Check("props", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(season.health_check())
    except Exception as exc:
        checks.append(Check("season", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(portfolio.health_check())
    except Exception as exc:
        checks.append(Check("portfolio", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(wpa.health_check())
    except Exception as exc:
        checks.append(Check("wpa", False, f"health_check() raised: {exc}"))
    from mlb_baseball import export, research

    try:
        checks.extend(research.health_check())
    except Exception as exc:
        checks.append(Check("research", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(export.health_check())
    except Exception as exc:
        checks.append(Check("export", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(calibration.health_check())
    except Exception as exc:
        checks.append(Check("calibration", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(drift.health_check())
    except Exception as exc:
        checks.append(Check("drift", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(backtest.health_check())
    except Exception as exc:
        checks.append(Check("backtest", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(ros.health_check())
    except Exception as exc:
        checks.append(Check("ros", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(stack.health_check())
    except Exception as exc:
        checks.append(Check("stack", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(parlay.health_check())
    except Exception as exc:
        checks.append(Check("parlay", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(stuff.health_check())
    except Exception as exc:
        checks.append(Check("stuff", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(heatmap.health_check())
    except Exception as exc:
        checks.append(Check("heatmap", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(neural.health_check())
    except Exception as exc:
        checks.append(Check("neural", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(pipeline.health_check())
    except Exception as exc:
        checks.append(Check("pipeline", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(visual.health_check())
    except Exception as exc:
        checks.append(Check("visual", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(cluster.health_check())
    except Exception as exc:
        checks.append(Check("cluster", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(dump.health_check())
    except Exception as exc:
        checks.append(Check("dump", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(hedge.health_check())
    except Exception as exc:
        checks.append(Check("hedge", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(bvp.health_check())
    except Exception as exc:
        checks.append(Check("bvp", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(umpire.health_check())
    except Exception as exc:
        checks.append(Check("umpire", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(weather.health_check())
    except Exception as exc:
        checks.append(Check("weather", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(bullpen.health_check())
    except Exception as exc:
        checks.append(Check("bullpen", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(reliever.health_check())
    except Exception as exc:
        checks.append(Check("reliever", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(chase_recog.health_check())
    except Exception as exc:
        checks.append(Check("chase_recog", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(first_pitch_ambush.health_check())
    except Exception as exc:
        checks.append(Check("first_pitch_ambush", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(wall_block.health_check())
    except Exception as exc:
        checks.append(Check("wall_block", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(heat_check.health_check())
    except Exception as exc:
        checks.append(Check("heat_check", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(putaway_depth.health_check())
    except Exception as exc:
        checks.append(Check("putaway_depth", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(outfield_target.health_check())
    except Exception as exc:
        checks.append(Check("outfield_target", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(oppo_gap.health_check())
    except Exception as exc:
        checks.append(Check("oppo_gap", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(spin_align.health_check())
    except Exception as exc:
        checks.append(Check("spin_align", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(dp_footwork.health_check())
    except Exception as exc:
        checks.append(Check("dp_footwork", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(pull_slice.health_check())
    except Exception as exc:
        checks.append(Check("pull_slice", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(fatigue_drop.health_check())
    except Exception as exc:
        checks.append(Check("fatigue_drop", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(first_step.health_check())
    except Exception as exc:
        checks.append(Check("first_step", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(high_heat.health_check())
    except Exception as exc:
        checks.append(Check("high_heat", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(ssw_latent.health_check())
    except Exception as exc:
        checks.append(Check("ssw_latent", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(bunt_charge.health_check())
    except Exception as exc:
        checks.append(Check("bunt_charge", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(air_trap.health_check())
    except Exception as exc:
        checks.append(Check("air_trap", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(intent_leak.health_check())
    except Exception as exc:
        checks.append(Check("intent_leak", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(lead_snap.health_check())
    except Exception as exc:
        checks.append(Check("lead_snap", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(zone_whiff.health_check())
    except Exception as exc:
        checks.append(Check("zone_whiff", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(active_spin.health_check())
    except Exception as exc:
        checks.append(Check("active_spin", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(low_scoop.health_check())
    except Exception as exc:
        checks.append(Check("low_scoop", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(slash_oppo.health_check())
    except Exception as exc:
        checks.append(Check("slash_oppo", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(arm_align.health_check())
    except Exception as exc:
        checks.append(Check("arm_align", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(wall_crash.health_check())
    except Exception as exc:
        checks.append(Check("wall_crash", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(ext_perceive.health_check())
    except Exception as exc:
        checks.append(Check("ext_perceive", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(foul_attrition.health_check())
    except Exception as exc:
        checks.append(Check("foul_attrition", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(block_suppress.health_check())
    except Exception as exc:
        checks.append(Check("block_suppress", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(pull_barrel.health_check())
    except Exception as exc:
        checks.append(Check("pull_barrel", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(putaway_exec.health_check())
    except Exception as exc:
        checks.append(Check("putaway_exec", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(route_burst.health_check())
    except Exception as exc:
        checks.append(Check("route_burst", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(rel_drift.health_check())
    except Exception as exc:
        checks.append(Check("rel_drift", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(exp_resist.health_check())
    except Exception as exc:
        checks.append(Check("exp_resist", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(catch_xchg.health_check())
    except Exception as exc:
        checks.append(Check("catch_xchg", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(pull_gb.health_check())
    except Exception as exc:
        checks.append(Check("pull_gb", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(vaa_toz.health_check())
    except Exception as exc:
        checks.append(Check("vaa_toz", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(ambush.health_check())
    except Exception as exc:
        checks.append(Check("ambush", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(blast_angle.health_check())
    except Exception as exc:
        checks.append(Check("blast_angle", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(velo_delta.health_check())
    except Exception as exc:
        checks.append(Check("velo_delta", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(arm_accuracy.health_check())
    except Exception as exc:
        checks.append(Check("arm_accuracy", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(gyro_spin.health_check())
    except Exception as exc:
        checks.append(Check("gyro_spin", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(two_strike.health_check())
    except Exception as exc:
        checks.append(Check("two_strike", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(pivot_dp.health_check())
    except Exception as exc:
        checks.append(Check("pivot_dp", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(contact_depth.health_check())
    except Exception as exc:
        checks.append(Check("contact_depth", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(arm_slot.health_check())
    except Exception as exc:
        checks.append(Check("arm_slot", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(catcher_pop.health_check())
    except Exception as exc:
        checks.append(Check("catcher_pop", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(xslg.health_check())
    except Exception as exc:
        checks.append(Check("xslg", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(velo_drift.health_check())
    except Exception as exc:
        checks.append(Check("velo_drift", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(catch_prob.health_check())
    except Exception as exc:
        checks.append(Check("catch_prob", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(pull_air.health_check())
    except Exception as exc:
        checks.append(Check("pull_air", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(haa.health_check())
    except Exception as exc:
        checks.append(Check("haa", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(bunt.health_check())
    except Exception as exc:
        checks.append(Check("bunt", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(babip.health_check())
    except Exception as exc:
        checks.append(Check("babip", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(vaa.health_check())
    except Exception as exc:
        checks.append(Check("vaa", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(iffb.health_check())
    except Exception as exc:
        checks.append(Check("iffb", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(sweetspot.health_check())
    except Exception as exc:
        checks.append(Check("sweetspot", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(putaway.health_check())
    except Exception as exc:
        checks.append(Check("putaway", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(wall.health_check())
    except Exception as exc:
        checks.append(Check("wall", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(zone_swing.health_check())
    except Exception as exc:
        checks.append(Check("zone_swing", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(fstrike.health_check())
    except Exception as exc:
        checks.append(Check("fstrike", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(poptime.health_check())
    except Exception as exc:
        checks.append(Check("poptime", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(clutch.health_check())
    except Exception as exc:
        checks.append(Check("clutch", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(arm.health_check())
    except Exception as exc:
        checks.append(Check("arm", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(diversity.health_check())
    except Exception as exc:
        checks.append(Check("diversity", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(spray.health_check())
    except Exception as exc:
        checks.append(Check("spray", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(tto.health_check())
    except Exception as exc:
        checks.append(Check("tto", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(carry.health_check())
    except Exception as exc:
        checks.append(Check("carry", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(damage.health_check())
    except Exception as exc:
        checks.append(Check("damage", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(bullpen_opt.health_check())
    except Exception as exc:
        checks.append(Check("bullpen_opt", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(fatigue.health_check())
    except Exception as exc:
        checks.append(Check("fatigue", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(splits.health_check())
    except Exception as exc:
        checks.append(Check("platoon", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(nrfi.health_check())
    except Exception as exc:
        checks.append(Check("nrfi", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(spin.health_check())
    except Exception as exc:
        checks.append(Check("spin", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(decision.health_check())
    except Exception as exc:
        checks.append(Check("decision", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(tunnel.health_check())
    except Exception as exc:
        checks.append(Check("tunnel", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(extension.health_check())
    except Exception as exc:
        checks.append(Check("extension", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(leverage.health_check())
    except Exception as exc:
        checks.append(Check("leverage", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(ssw.health_check())
    except Exception as exc:
        checks.append(Check("ssw", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(blocking.health_check())
    except Exception as exc:
        checks.append(Check("blocking", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(travel.health_check())
    except Exception as exc:
        checks.append(Check("travel", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(api.health_check())
    except Exception as exc:
        checks.append(Check("api", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(baserunning.health_check())
    except Exception as exc:
        checks.append(Check("baserunning", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(entropy.health_check())
    except Exception as exc:
        checks.append(Check("entropy", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(aging.health_check())
    except Exception as exc:
        checks.append(Check("aging", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(shop.health_check())
    except Exception as exc:
        checks.append(Check("shop", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(count.health_check())
    except Exception as exc:
        checks.append(Check("count", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(shift.health_check())
    except Exception as exc:
        checks.append(Check("shift", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(sub.health_check())
    except Exception as exc:
        checks.append(Check("sub", False, f"health_check() raised: {exc}"))
    try:
        checks.extend(daemon.health_check())
    except Exception as exc:
        checks.append(Check("daemon", False, f"health_check() raised: {exc}"))

    # backup.py has no bootstrap()/update() either -- it's an operational
    # tool, not a data source, but a missing pg_dump/psql should still show
    # up here rather than as a surprise the first time someone runs
    # `mlb backup`.
    try:
        checks.extend(backup.health_check())
    except Exception as exc:
        checks.append(Check("backup", False, f"health_check() raised: {exc}"))

    return checks

from __future__ import annotations

SCHEMA = (
    """
    create table if not exists workflows (
        workflow_id text primary key,
        name text not null,
        spec_path text not null,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists runs (
        run_id text primary key,
        workflow_id text not null,
        status text not null,
        inputs_json text not null,
        current_step_id text,
        failed_step_id text,
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp,
        completed_at text,
        foreign key (workflow_id) references workflows(workflow_id)
    )
    """,
    """
    create table if not exists steps (
        run_id text not null,
        step_id text not null,
        step_order integer not null,
        step_type text not null,
        status text not null,
        attempt integer not null default 0,
        outputs_json text not null default '[]',
        error_json text,
        started_at text,
        completed_at text,
        locked_by text,
        locked_at text,
        primary key (run_id, step_id),
        foreign key (run_id) references runs(run_id)
    )
    """,
    """
    create table if not exists artifacts (
        artifact_id integer primary key autoincrement,
        run_id text not null,
        step_id text not null,
        path text not null,
        kind text not null,
        created_at text not null default current_timestamp,
        unique (run_id, step_id, path),
        foreign key (run_id, step_id) references steps(run_id, step_id)
    )
    """,
    """
    create table if not exists events (
        event_id integer primary key autoincrement,
        run_id text not null,
        step_id text,
        event_type text not null,
        message text not null,
        payload_json text not null default '{}',
        created_at text not null default current_timestamp,
        foreign key (run_id) references runs(run_id)
    )
    """,
    """
    create table if not exists approvals (
        approval_id integer primary key autoincrement,
        run_id text not null,
        step_id text not null,
        decision text not null,
        reviewer text not null,
        notes text not null,
        created_at text not null default current_timestamp,
        unique (run_id, step_id),
        foreign key (run_id, step_id) references steps(run_id, step_id)
    )
    """,
    """
    create table if not exists kb_updates (
        kb_update_id integer primary key autoincrement,
        run_id text not null,
        step_id text not null,
        client text not null,
        path text not null,
        status text not null,
        content text not null,
        created_at text not null default current_timestamp,
        foreign key (run_id, step_id) references steps(run_id, step_id)
    )
    """,
    # Migration + idempotency for kb_updates: collapse any pre-existing duplicates (kept the
    # earliest row per key) BEFORE creating the unique index, so the index never fails on a
    # dirty DB and bricks initialize(). The index is the ON CONFLICT target used by
    # record_kb_update and also migrates older DBs created before it existed.
    """
    delete from kb_updates
    where kb_update_id not in (
        select min(kb_update_id) from kb_updates group by run_id, step_id, path
    )
    """,
    """
    create unique index if not exists idx_kb_updates_unique
    on kb_updates (run_id, step_id, path)
    """,
)

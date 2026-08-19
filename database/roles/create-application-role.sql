-- TDMS least-privilege application database role — PROPOSAL, NOT YET APPLIED.
--
-- Run this only after the privileges below have been approved. It is written to
-- be idempotent, so re-running it is safe.
--
-- Architecture (Access Model v1.1 §52):
--
--     TDMS users  ->  application-level RBAC  ->  FastAPI
--                                                    |
--                                   one controlled application identity
--                                                    v
--                                               PostgreSQL
--
-- There is deliberately NO PostgreSQL login per TDMS user. A TDMS Super Admin is
-- an application role, not a database login, and mapping the two would put
-- authorisation in two places that can disagree.
--
-- Migrations keep using the administrator credentials. The application role
-- cannot create, alter or drop anything, so a bug in a request handler cannot
-- rewrite the schema.

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- 1. The role
-- ---------------------------------------------------------------------------
-- The password is supplied by the caller as :app_password and never stored in
-- this file:
--     psql -v app_password="$TDMS_POSTGRES_APP_PASSWORD" -f create-application-role.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tdms_app') THEN
        CREATE ROLE tdms_app LOGIN;
    END IF;
END
$$;

ALTER ROLE tdms_app WITH PASSWORD :'app_password';

-- Explicitly withheld: SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS.
ALTER ROLE tdms_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- ---------------------------------------------------------------------------
-- 2. Connect and read the schema
-- ---------------------------------------------------------------------------

GRANT CONNECT ON DATABASE tdms_dev TO tdms_app;
GRANT USAGE ON SCHEMA public TO tdms_app;

-- No CREATE on the schema: the application may not add tables, and in
-- PostgreSQL 15+ PUBLIC no longer holds it by default. Revoked anyway, so the
-- intent is explicit rather than inherited from a version default.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM tdms_app;

-- ---------------------------------------------------------------------------
-- 3. Business tables — full row-level access
-- ---------------------------------------------------------------------------
-- DELETE is granted even though business records are soft-deleted (DATA-04),
-- because import staging rows are genuinely removed once a batch is finalised.

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO tdms_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tdms_app;

-- ---------------------------------------------------------------------------
-- 4. LOG-05 — the activity record is append-only, enforced by privilege
-- ---------------------------------------------------------------------------
-- This is the point of the whole exercise. "We never update activity records"
-- is a convention; a role that CANNOT update them is a control. An attacker who
-- reaches the application connection still cannot erase what they did.

REVOKE UPDATE, DELETE ON user_activity_records FROM tdms_app;

-- Alembic's bookkeeping belongs to migrations, not to the application.
REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM tdms_app;

-- ---------------------------------------------------------------------------
-- 5. Future tables created by migrations
-- ---------------------------------------------------------------------------
-- Without this, every new migration would silently produce a table the
-- application cannot read, and the failure would appear at runtime rather than
-- at deployment.

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tdms_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO tdms_app;

-- ---------------------------------------------------------------------------
-- 6. Verify
-- ---------------------------------------------------------------------------

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
FROM pg_roles WHERE rolname = 'tdms_app';

SELECT 'user_activity_records' AS table_name,
       has_table_privilege('tdms_app', 'user_activity_records', 'SELECT') AS can_select,
       has_table_privilege('tdms_app', 'user_activity_records', 'INSERT') AS can_insert,
       has_table_privilege('tdms_app', 'user_activity_records', 'UPDATE') AS can_update,
       has_table_privilege('tdms_app', 'user_activity_records', 'DELETE') AS can_delete;
-- Expected: can_select t, can_insert t, can_update f, can_delete f.

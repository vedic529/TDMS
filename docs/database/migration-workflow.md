# TDMS Migration Workflow

How to change the TDMS database. Every structural change reaches PostgreSQL through
an Alembic migration in Git — never through `psql`, a GUI, or `create_all()`.

All commands run from **`apps/api`** with the virtual environment activated.

```powershell
cd C:\TDMS\apps\api
.\.venv\Scripts\Activate.ps1
```

The database must be running first:

```bash
docker compose up -d db
```

---

## 1. Where the connection details come from

`alembic.ini` has **`sqlalchemy.url =` deliberately empty**. `alembic/env.py`
resolves the URL at runtime from `app.core.config`, which reads `DATABASE_URL` if
set, otherwise composes one from the `TDMS_POSTGRES_*` variables in the repository
`.env` file.

That file is git-ignored. **Never** put a password into `alembic.ini`, a Python
module, a Dockerfile, the README, or any other tracked file.

`env.py` also accepts a one-off override, used only for throwaway test databases:

```bash
alembic -x db_url=postgresql+psycopg://<user>:<password>@<host>:5432/<database> upgrade head
```

---

## 2. Everyday commands

| Command | What it does |
| --- | --- |
| `alembic current` | Which revision the database is on |
| `alembic history --verbose` | Full revision history |
| `alembic heads` | The latest revision(s) in the scripts folder |
| `alembic upgrade head` | Apply everything outstanding |
| `alembic downgrade -1` | Undo the most recent migration |
| `alembic check` | Does the database match the models? |
| `alembic upgrade head --sql` | Print the SQL without running it |

---

## 3. Changing the schema

1. **Confirm the change is approved.** The documents in `docs/database/` are the
   source of truth. If a change contradicts them, stop and get the design updated
   first — do not resolve a design question inside a migration.

2. **Edit the model** in `apps/api/app/models/`. If you add a *new module*, import
   it in `app/models/__init__.py` and add the table to `EXPECTED_TABLES`. A model
   that is never imported is invisible to autogeneration.

3. **Autogenerate the migration:**

   ```bash
   alembic revision --autogenerate -m "short description of the change"
   ```

4. **Review the generated file line by line — this step is not optional.**
   Autogeneration is a first draft. Check specifically for:
   - tables or columns it dropped that you did not intend to drop;
   - a column rename rendered as `drop_column` + `add_column`, which destroys data
     (replace it with `op.alter_column(..., new_column_name=...)`);
   - `server_default` on a new `NOT NULL` column on a table that already has rows;
   - things Alembic cannot see at all (see §4);
   - a `downgrade()` that actually reverses the upgrade.

5. **Apply it:**

   ```bash
   alembic upgrade head
   ```

6. **Prove it round-trips:**

   ```bash
   alembic downgrade -1
   alembic upgrade head
   alembic check
   ```

   `alembic check` must report *No new upgrade operations detected*.

7. **Update the tests** in `tests/test_schema_v1.py` and run `pytest`.

8. **Commit the model change and the migration together**, in the same commit.

---

## 4. What Alembic cannot autogenerate

Add these by hand, with a comment explaining why, following the pattern already in
the initial migration:

- **Extensions** — `op.execute("CREATE EXTENSION IF NOT EXISTS …")`.
- **Views** — `op.execute("CREATE VIEW …")` on upgrade and `DROP VIEW` on
  downgrade, dropped *before* the tables it depends on.
- **Enum type drops** — enum types are created implicitly with the first table that
  uses them, but `drop_table` does not remove them. A downgrade must drop them
  explicitly, *after* the tables, or the next `upgrade head` fails with "type
  already exists".
- **Adding a value to an existing enum** — `ALTER TYPE … ADD VALUE` cannot run
  inside a transaction block in older PostgreSQL and cannot be reversed; prefer a
  lookup table when a domain is likely to grow.
- **Data migrations** — write them explicitly with `op.execute` or a bulk update.

---

## 5. Verifying a rebuild from scratch

Before any release, prove that a blank database can be built from migrations alone.
Create an empty database, point Alembic at it with `-x db_url=…`, run
`upgrade head`, compare the inventory against `EXPECTED_TABLES` / `EXPECTED_VIEWS`,
then drop it. The counts must match the development database exactly. See
`schema-v1-implementation.md` §5 for the recorded result.

---

## 6. Rules

- Never edit a migration that has been applied anywhere but your own machine —
  write a new one.
- Never let two branches create sibling revisions with the same `down_revision`
  unless you intend to merge them (`alembic merge`).
- Never use `Base.metadata.create_all()` against a real database. It bypasses the
  version table, and the schema then has no recorded history.
- Never run `docker compose down -v` casually — the `-v` destroys the
  `tdms_postgres_data` volume and every row in it.
- Keep `downgrade()` genuinely reversible. A downgrade that silently drops data is
  worse than one that raises `NotImplementedError` with an explanation.

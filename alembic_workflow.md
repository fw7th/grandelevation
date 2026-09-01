# Managing the database with Alembic

Now that `create_all()` is gone, Alembic is the only thing allowed to
change the database schema. This is the day-to-day reference for how
that actually works.

## The mental model

- `models.py` is the *desired* schema — what your Python code thinks
  the database should look like.
- The database itself is the *actual* schema — what tables/columns
  really exist right now.
- A migration is a small script that moves the actual schema one step
  closer to the desired schema. Alembic tracks which migrations have
  already been applied via a table it creates in your DB called
  `alembic_version`.
- `create_all()` only ever did "create tables that don't exist yet."
  It never handled altering existing tables. Alembic replaces that
  with real diffs: add a column, drop a column, change a type, add an
  index, etc.

## Every time you change models.py

1. Make your change in `models.py` (add a field, add a new table
   class, rename something, etc).
2. Generate a migration:
   ```
   uv run alembic revision --autogenerate -m "add warranty_months to product"
   ```
   Use a short, descriptive message — it becomes part of the
   filename and the changelog you'll scroll through later.
3. **Open the generated file** in `alembic/versions/` and actually
   read it. Autogenerate is good but not perfect — it will:
   - Miss changes to column defaults or server-side defaults in
     some cases.
   - Sometimes generate a drop+recreate for a column when a simple
     `ALTER COLUMN TYPE` would do (worth fixing manually if you're
     changing types on a table with real data).
   - Not detect data migrations — if you're renaming a column,
     autogenerate sees it as "drop old column, add new column" and
     will silently lose that column's data unless you edit the
     migration to rename in place instead.
4. Test it locally:
   ```
   uv run alembic upgrade head
   ```
   This applies every migration that hasn't run yet, in order, up
   to the latest one ("head").
5. Check your local DB looks right (open a client, check the table).
6. Commit the migration file along with your `models.py` change —
   they're one logical unit and should land in the same PR/commit.
7. Deploy. Run the same `alembic upgrade head` against production
   (see "Deploying migrations" below) either just before or just
   after your code deploy, depending on whether the migration is
   backwards-compatible with the currently-running code.

## Adding a new table

Same flow as above — add the new `SQLModel` class (with `table=True`)
to `models.py`, then `alembic revision --autogenerate`. Alembic will
generate a `create_table` migration. No special handling needed.

## Adding a column

Add the field to the model class, then autogenerate. Watch out for:

- **Non-nullable columns on a table that already has rows.** If you
  add `warranty_months: int` (no default) to `Product` and there are
  existing rows, the migration will fail on `upgrade head` because
  Postgres has no value to put in the new column for old rows. Fix
  by either:
  - Giving it a default: `warranty_months: int = Field(default=12)`
    — Alembic will include that default in the migration.
  - Or making it optional at first: `warranty_months: int | None =
    None`, backfilling data in a follow-up step, then tightening it
    to non-nullable in a later migration once every row has a value.

## Removing a column or table

Autogenerate will produce a `drop_column` / `drop_table` migration.
Before running `upgrade head` in production, make sure:

- No code still reads/writes that column — deploy the code change
  removing all usage *before* running the migration that drops it,
  never the other way around, or your running app will crash trying
  to read a column that no longer exists.
- You actually want the data gone. Alembic migrations can be
  downgraded (see below), but a dropped column's data is not
  restored by downgrading — the data itself is gone, only the
  column shape comes back empty.

## Renaming things

Autogenerate does **not** detect renames — it sees a renamed column
as "old column dropped, new column added," which loses data. If you
rename a column or table, edit the generated migration by hand to
use `op.alter_column(..., new_column_name=...)` or
`op.rename_table(...)` instead of the drop/add pair Alembic
generated.

## Rolling back

If a migration causes a problem after deploying:

```
uv run alembic downgrade -1
```

This undoes the single most recent migration by running its
`downgrade()` function (auto-generated alongside `upgrade()`).
Check the migration file's `downgrade()` before relying on this in
a real incident — for destructive changes (dropped columns/tables),
`downgrade()` can restore the *shape* but never the data that was
in it at drop time.

## Useful commands

| Command | What it does |
|---|---|
| `uv run alembic current` | Shows which migration the DB is currently on |
| `uv run alembic history` | Lists all migrations in order |
| `uv run alembic upgrade head` | Applies all pending migrations |
| `uv run alembic upgrade +1` | Applies just the next pending migration |
| `uv run alembic downgrade -1` | Reverts the most recent migration |
| `uv run alembic revision --autogenerate -m "msg"` | Generates a new migration from model changes |
| `uv run alembic stamp head` | Marks the DB as up-to-date *without* running any DDL (only for baselining an existing DB — never use this to "fix" a failed migration) |

## Deploying migrations

You have two DBs to keep in sync: local Postgres and Nhost
(production). Locally, you run `upgrade head` yourself whenever you
pull a new migration. For production, decide on one of:

- **Manual**: after deploying new code, SSH/connect with
  `NHOST_DATABASE_URL` pointed at prod and run `uv run alembic
  upgrade head` by hand. Simple, but easy to forget.
- **Automated as part of deploy**: add a pre-deploy or post-deploy
  step (Vercel build step, or a small script) that runs `alembic
  upgrade head` against `NHOST_DATABASE_URL` automatically. Safer
  once your deploy process is stable, but means a bad migration can
  block or break a deploy — make sure you're comfortable reading
  and testing migrations locally first before automating this.

Either way: **never run `upgrade head` against prod without having
run it locally first.** Local is where you catch the autogenerate
mistakes described above.

## Things that will bite you if forgotten

- If you add a table class to `models.py` but never import that
  module somewhere Alembic's `env.py` sees it, autogenerate won't
  know the table exists and won't generate anything for it. Your
  `env.py` imports your models module for exactly this reason —
  don't remove that import.
- Two people generating migrations at the same time from the same
  starting point creates two migration files with the same "down
  revision," which Alembic can't apply in order. If you're working
  with anyone else on this, pull latest and regenerate rather than
  rebasing an old migration file.
- `alembic stamp head` never runs DDL. If you use it on a DB that
  does *not* already match your models (as opposed to the one-time
  baseline you already did), you'll have a DB and a migration
  history that silently disagree — future migrations will look
  fine to Alembic but fail against the real schema. Only use
  `stamp` for the initial baseline, never as a shortcut later.

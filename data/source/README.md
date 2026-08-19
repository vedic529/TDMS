# Approved source data

The workbooks the reference importers read. They live here so every script
resolves one stable path instead of pointing at somebody's `Downloads` folder.

**Nothing in this folder is committed.** `.gitignore` excludes everything except
this README. The files carry student, staff and college records, and the GitHub
repository is public — so the rule is absolute, not a preference.

## Expected files

| File | Feeds |
| --- | --- |
| `Location Data.xlsx` | Colleges, campuses, college–campus links, campus address spellings, course offerings |
| `Qualification Data.xlsx` | Qualifications, units, unit memberships |
| `Trainer Data - BSB.xlsx` | Trainers, weekly availability, qualification and unit competencies |
| `Rolling TT Data.xlsx` | Course duration cycles |

A missing file is reported by name when a script starts, rather than failing
part-way through a load.

## Replacing a workbook

Drop the new version in with the same file name and re-run the importer. Start
with a dry run — that is the default, and it reports what would change without
writing:

```
cd apps/api
python scripts/import_reference_data.py            # dry run, rolls back
python scripts/import_reference_data.py --apply    # writes
```

The importers are idempotent: re-running one does not duplicate rows.

## Using a different location

Set `TDMS_SOURCE_DATA_DIR` to an absolute path and every script reads from there
instead. Useful for a shared drive, or for testing a revised workbook without
disturbing the approved one:

```
TDMS_SOURCE_DATA_DIR=D:\shared\tdms-source python scripts/import_reference_data.py
```

## What does not belong here

Student lists. They are not reference data, they are not loaded by these
scripts, and `.gitignore` carries separate rules matching student file names
wherever they appear in the tree. Keep them outside the repository.

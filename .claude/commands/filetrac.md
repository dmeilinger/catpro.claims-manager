Query FileTrac for: $ARGUMENTS

Run `python3.13 backend/scripts/ft_query.py` from the repo root. The script manages the session automatically — it logs in with one TOTP only if the saved session has expired.

---

## Map the question to the right subcommand

### `summary` — overall open claims breakdown
Use when asked for a general overview, totals, or "what's going on".
```
python3.13 backend/scripts/ft_query.py summary
```

### `list` — filtered claim list
Use for any specific query. Combine flags freely.
```
python3.13 backend/scripts/ft_query.py list [flags]
```

| Flag | Values | Example |
|---|---|---|
| `--status` | `OPEN` (default), `CLOSED`, `BOTH` | `--status BOTH` |
| `--adjuster` | adjuster name | `--adjuster "Brian Lara"` |
| `--file-status` | see status values below | `--file-status "Pending Inspection"` |
| `--company` | `acuity`, `auto-owners`, `allstate`, `test` | `--company acuity` |
| `--branch` | `main`, `allstate`, `test` | `--branch main` |
| `--loss-type` | Hail, Wind, Fire, Water, etc. | `--loss-type Hail` |
| `--overdue` | (flag, no value) | `--overdue` |
| `--group-by` | `adjuster`, `status`, `client` | `--group-by adjuster` |

**File status values:** `Intitial Contact` · `Pending Inspection` · `Inspected - Pending Docs` · `Ready for Review` · `Being Reviewed` · `Returned for Corrections` · `Review Complete` · `Pending Reinspection` · `Pending Client Response` · `File Re-Opened` · `Closed`

**Common examples:**
```
python3.13 backend/scripts/ft_query.py list --group-by adjuster
python3.13 backend/scripts/ft_query.py list --file-status "Pending Inspection"
python3.13 backend/scripts/ft_query.py list --company acuity --group-by adjuster
python3.13 backend/scripts/ft_query.py list --overdue
python3.13 backend/scripts/ft_query.py list --status BOTH --adjuster "Chase Webb"
python3.13 backend/scripts/ft_query.py list --loss-type Hail --group-by status
```

### `claim <file-number>` — single claim detail
```
python3.13 backend/scripts/ft_query.py claim 26-10113
```

---

Present the script output directly to the user. If a login occurred, mention it so the user knows a TOTP code was used.

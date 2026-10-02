# Running the pipeline daily with Windows Task Scheduler

The pipeline is a normal command-line program; Task Scheduler only needs to start it once a day.
Everything it writes (state, CSV, log) goes to `99_LOGS_QC`, so it works with no one logged in.

> **Note:** these commands were written and reviewed on a Linux development machine and could not be
> executed on Windows there. Step 5 (run it once by hand and read the log) is how you verify them on your PC.

## 0. Before you schedule anything

1. Install Python 3.10+ (64-bit), then `pip install -r requirements.txt`.
2. Install ffmpeg and check `ffmpeg -version` and `ffprobe -version` work.
3. Copy `config.example.json` to `config.json`, edit it, and **run a dry run by hand first** (see README).
   Set `"require_approval": false` explicitly for unattended real runs: the default `true` requires someone to type `yes` when videos are eligible. A run with no eligible videos prints the report and exits without prompting. Do not use `--yolo` merely to skip approval: it also disables the stability-minute wait for that invocation (transfer-file blocking and the growth re-check remain).
   The optional `"video_description": null` leaves output filenames unchanged. A filename-safe value such as `"pilot visit"` adds `_pilot_visit` after the ID to the mom, child and optional side-by-side output names. Changing this after syncing requires `--reprocess` to archive prior outputs.
4. Run one real run by hand on a test participant and read `99_LOGS_QC\pipeline_status.csv`.
5. Find the explicit paths you will use (do not rely on `PATH`, which a scheduled task may not see):

```bat
where python
where ffmpeg
where ffprobe
```

Put the absolute ffmpeg/ffprobe paths in `config.json` (`"ffmpeg": "C:\\Tools\\ffmpeg\\bin\\ffmpeg.exe"`,
same for `ffprobe`) so the task cannot fail with "ffmpeg not found".

Suppose (edit to your machine):

| Item | Example |
|---|---|
| Python | `C:\Users\YOU\AppData\Local\Programs\Python\Python312\python.exe` |
| Repository | `C:\RG2019\research-video-sync` |
| Config | `C:\RG2019\config.json` *(keep it outside the repository, or it is git-ignored anyway)* |

## 1. Create the task from the command line (recommended)

Open **Command Prompt** (not PowerShell) as the user who owns the project and run, on one line:

```bat
schtasks /Create /TN "RG2019 daily video sync" /SC DAILY /ST 02:00 /RL LIMITED /F ^
  /TR "\"C:\Users\YOU\AppData\Local\Programs\Python\Python312\python.exe\" \"C:\RG2019\research-video-sync\pipeline_rg2019.py\" --config \"C:\RG2019\config.json\""
```

* `/ST 02:00` = 02:00 every night. Pick a time when nobody uses the machine.
* Add `/RU YOUR_WINDOWS_USER /RP *` if you want it to run **whether or not you are logged on**
  (you will be asked for your Windows password once; it is stored by Windows, not by the script).
* Quotes matter: each path is wrapped in `\"..\"` because of spaces.

## 2. Or create it in the GUI

1. Start menu -> **Task Scheduler** -> *Create Task...* (not "Basic Task").
2. **General**: name `RG2019 daily video sync`; choose **Run whether user is logged on or not**;
   leave "Run with highest privileges" off.
3. **Triggers** -> New -> *Daily*, 02:00, recur every 1 day.
4. **Actions** -> New -> *Start a program*
   * Program/script: `C:\Users\YOU\AppData\Local\Programs\Python\Python312\python.exe`
   * Add arguments: `"C:\RG2019\research-video-sync\pipeline_rg2019.py" --config "C:\RG2019\config.json"`
   * Start in: `C:\RG2019\research-video-sync`
5. **Conditions**: untick *Start the task only if the computer is on AC power* if this is a laptop;
   consider *Wake the computer to run this task*.
6. **Settings**: tick *Run task as soon as possible after a scheduled start is missed*;
   set *If the task is already running: **Do not start a new instance***;
   set *Stop the task if it runs longer than* to something generous (e.g. 12 hours) or untick it -
   a long backlog of encodes is normal, and the pipeline is safe to interrupt and resume.

## 3. Logging with nobody logged on

* The pipeline writes its own log file: `FOLLOWUP_ROOT\99_LOGS_QC\logs\pipeline_YYYY-MM-DD.log`
  (UTF-8, appended), plus per-participant state in `99_LOGS_QC\state\` and `pipeline_status.csv`.
* The end-of-run summary (newly completed / skipped / waiting / manual review / failed, with IDs) is
  written to that log when processing starts. If no videos are eligible, the pre-run report is printed to standard output before the command exits; capture standard output if you need to retain those reports.
* Optional: also capture anything printed before logging starts (e.g. a Python crash) by wrapping the
  command in `cmd /c` with redirection:

```bat
schtasks /Create /TN "RG2019 daily video sync" /SC DAILY /ST 02:00 /F ^
  /TR "cmd /c \"\"C:\Users\YOU\...\python.exe\" \"C:\RG2019\research-video-sync\pipeline_rg2019.py\" --config \"C:\RG2019\config.json\" >> \"C:\RG2019\scheduler_stdout.txt\" 2>&1\""
```

  (Keep that redirect file outside the synced project folder, or it will be uploaded to the NAS.)

## 4. Exit codes ("Last Run Result" column)

| Code | Meaning |
|---|---|
| `0x0` | Finished; nothing needs a human (waiting participants are normal). |
| `0x1` | A real run with eligible videos was cancelled at the approval prompt (set `require_approval` to `false` for unattended tasks). |
| `0x2` | Finished, but at least one participant needs **manual review** or **failed** - read the log. |
| `0x3` | Nothing was processed: config error, `ffmpeg`/`ffprobe` missing, project drive not available, or another run holds the lock. |

## 5. Test it

```bat
schtasks /Run /TN "RG2019 daily video sync"
schtasks /Query /TN "RG2019 daily video sync" /V /FO LIST
```

then open today's file in `99_LOGS_QC\logs`. To switch it off: `schtasks /Change /TN "RG2019 daily video sync" /DISABLE`.

## 6. Good practice

* Start with a **dry-run task** (add `--dry-run` to the arguments) for a few days and read what it *would* do.
* If a run crashes or the PC loses power, just let the next run happen: interrupted work resumes.
  A run keeps `99_LOGS_QC\pipeline.lock` fresh with a heartbeat, so a long backlog is never taken over by the next scheduled start; a lock that has not been refreshed for `lock_stale_hours` (default 24 h, i.e. the run crashed) is replaced automatically;
  if you are sure nothing is running and want to run sooner, delete that one file.
* In Synology Drive Client you may exclude `*.partial` and `*.tmp` from syncing so half-written videos are not uploaded.
* Windows Update reboots and sleep can interrupt a run; that is safe, but choose a time outside your update window.

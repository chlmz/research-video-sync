# Beginner's guide: running the video-sync tool from the command line

This guide is for Windows users who want to run the video-sync pipeline from a terminal after getting its code from GitHub. The production tool is `pipeline_rg2019.py`. **Do not run the `.sh` scripts**; they are legacy scripts and are not for the current workflow.

The pipeline moves original videos from `00_INBOX` into `01_RAW`, then creates synchronized outputs under `02_SYNCED`. Treat a real run as a file operation, not just a preview.

## 1. Prerequisites

Install these before running the pipeline:

| Requirement | Why it is needed |
|---|---|
| **Git for Windows** | Downloads (clones) the project from GitHub. |
| **Python 3.10 or newer** | Runs the pipeline. During installation, enable the option to add Python to `PATH` if offered. |
| **FFmpeg, including `ffprobe`** | Reads and encodes the video and audio. The FFmpeg build must support `libx264` and AAC. |

Install Git and Python from their official websites, and install FFmpeg using your organization's approved method. The commands below use Windows Command Prompt. Open a new Command Prompt after installing, then check that Git and Python are available:

```bat
git --version
python --version
```

Python should report version 3.10 or newer. If either command is not recognized, install the missing program or correct its `PATH` before continuing. FFmpeg and `ffprobe` must also be available on `PATH`, or their full paths must be set in the configuration file.

> The project has not been tested on Windows itself. If you encounter platform-specific problems, check the troubleshooting section below and the project README.

## 2. Get the project from GitHub

Choose a folder where you want to keep the program, open Command Prompt, and run:

```bat
git clone https://github.com/chmlz/research-video-sync.git
cd research-video-sync
```

or 

```bat
git clone https://github.com/sgbstats/research-video-sync.git
cd research-video-sync
```

If the repository is **already cloned**, do not clone it again; open Command Prompt and change to that existing `research-video-sync` folder instead.

## 3. Install the Python packages

From the repository folder, run:

```bat
python -m pip install -r requirements.txt
```

This installs the required NumPy and SciPy packages. If `python` is not recognized but the Python launcher is installed, try using `py` in place of `python` in the commands in this guide.

## 4. Set up your configuration

Create a local configuration and the default follow-up folder structure in one step:

```bat
python pipeline_rg2019.py --setup "D:\RG2019_CAMERAS\FOLLOWUP_2026"
notepad config.json
```

`--setup` copies the project defaults into `config.json`, sets `followup_root` to the supplied path, and creates the configured folders if missing. An absolute path is recommended. If the config already exists, setup asks before replacing it; answering `yes` continues folder creation, while any other response cancels without changes. You can choose a different config destination with `--config`, for example `python pipeline_rg2019.py --setup "D:\RG2019_CAMERAS\FOLLOWUP_2026" --config "D:\settings\rg2019.json"`.

If setting up manually instead, set `followup_root` in `config.json` to the full path of your actual project data folder. For example:

```json
"followup_root": "D:\\RG2019_CAMERAS\\FOLLOWUP_2026"
```

Use your own correct path; the example path is not a real location. The project folder should contain `00_INBOX`, where incoming participant folders arrive. By default, the pipeline also uses `01_RAW`, `02_SYNCED`, and `99_LOGS_QC` beneath that root. If FFmpeg is not on `PATH`, edit the `ffmpeg` and `ffprobe` settings to their full executable paths.

Keep `config.json` private to your machine. It is intentionally excluded from Git; only the example configuration should be committed.

### Local conventions

For WCHADS data, change the config.json to:

```json
  "participant_id_regex": "^#\\d{4,8}$",
  "mom_pattern": "mum view point",
  "child_pattern": "teen view point",
  "create_side_by_side": true
```

## 5. Preview the run first

Always start with a dry run:

```bat
python pipeline_rg2019.py --config config.json --dry-run
```

Read the output and make sure the folders and participant videos it identifies are the ones you expect. A dry run creates any missing configured top-level folders under `followup_root`, lists video files in valid participant folders whose extensions match the configured video suffixes, and reports videos in folders waiting for stability with the pipeline's reason. A real run first prints a pre-run inventory of source videos to sync and those skipped or blocked (including missing/ambiguous matches, unsupported suffixes, and already-synced participants), then requires you to type `yes` before starting. Any other response cancels without starting processing and returns exit code `1`.

With the default settings, a new participant can remain in a waiting status during a dry run. That is expected: the default stability check requires a prior **real** run to have observed the files unchanged. Repeating dry runs will not satisfy that check because dry runs do not save observations. The README explains how to do a one-off pilot dry run without changing files.

## 6. Run the pipeline

Only after reviewing the dry-run output, start a real run:

```bat
python pipeline_rg2019.py --config config.json
```

The pipeline waits until incoming files appear stable. With the default configuration, files must be at least 120 minutes old and must have been observed unchanged during an earlier real run; consequently, a new participant will normally wait until a later run. Transfer-in-progress files also block processing.

The pipeline accepts pairs directly in `00_INBOX` or in nested folders. Each participant ID needs exactly one `_mom` and one `_child` video in the same folder; the ID comes from the filenames or, if absent there, the folder path. Multiple ID pairs may share a folder. Source folders are preserved in `01_RAW` and `02_SYNCED`; status and logs are recorded under `99_LOGS_QC`. **Do not edit files in `01_RAW`.**

## 7. Useful command options

Replace `ID100392` with the participant ID you intend to process.

| What you want to do | Example |
|---|---|
| Process only one participant | `python pipeline_rg2019.py --config config.json --participant ID100392` |
| Preview one participant | `python pipeline_rg2019.py --config config.json --participant ID100392 --dry-run` |
| Reprocess a participant from `01_RAW` | `python pipeline_rg2019.py --config config.json --participant ID100392 --reprocess ID100392` |
| Show more diagnostic detail | `python pipeline_rg2019.py --config config.json --log-level DEBUG` |

Reprocessing archives known previous outputs under a `_superseded_...` folder rather than deleting them. A manual offset should only be used after reviewing the videos and deciding the correct offset. It requires exactly one `--participant`; a positive offset trims the mother video, and a negative offset trims the child video. See the README for the full command and details.

## 8. Check results and troubleshoot

Look at `99_LOGS_QC\\pipeline_status.csv` for the participant statuses and messages. The dated log files are in `99_LOGS_QC\\logs`. The command exits with code `0` when no human action is needed, `2` when something needs review or failed, and `3` for a configuration, tool, or lock problem.

Common problems:

| Message or situation | What to check |
|---|---|
| `ffmpeg was not found` | Install FFmpeg or set full paths for `ffmpeg` and `ffprobe` in `config.json`. |
| Participant stays in a waiting status | Check `pipeline_status.csv` and the log. Waiting on a new participant is expected with the default prior-observation setting. |
| `MISSING_FILES` or `AMBIGUOUS_FILES` | Confirm there is exactly one `_mom` video and one `_child` video in the participant's inbox folder. |
| `LOW_CONFIDENCE` | Review the recordings and status details; do not assume the estimated offset is correct. See the README before reprocessing or using a manual offset. |
| `PROMOTE_FAILED` | A file may be locked by another program. Close it and run the pipeline again. `00_INBOX` and `01_RAW` must be on the same volume. |

## More information

The repository's [README](../README.md) describes readiness rules, synchronization behavior, statuses, and manual reprocessing in more detail. For automatic daily runs, see [Windows Task Scheduler setup](WINDOWS_TASK_SCHEDULER.md).

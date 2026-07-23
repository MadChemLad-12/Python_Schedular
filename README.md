# Python_Schedular

A local job queue runner for CP2K (and VASP) calculations, built to replace an HPC scheduler after losing allocation access on Fugaku. Runs sequential DFT jobs on a single Linux workstation, with crash protection, live progress notifications, and automatic post-processing of results.

## Why this exists

After my Fugaku HPC team allocation ran out, I still had a backlog of CP2K single-point and geometry optimisation calculations to run for active-learning MLIP training data. With no SLURM/PBS scheduler available, I needed something to:

- work through a queue of jobs unattended on a local workstation,
- not die silently if one job crashed, ran out of memory, or hung,
- tell me what happened without me needing to babysit a terminal, and
- give me a quick sanity check (energy convergence, final structure) without manually opening output files.

This repo is what came out of that.

## What's in here

| File | Purpose |
|---|---|
| `cp2k_job_runner_final.py` | Main scheduler: runs a queue of CP2K jobs from a CSV, one at a time, with crash handling, notifications, energy plots, and CIF export. |
| `cp2k_vasp_job_runner.py` | Extended version supporting a mixed CP2K/VASP job queue. |
| `notification_config.json` | Template config for email / Slack / Teams / LINE Works notifications. |
| `example_input.csv` | Example job queue for `cp2k_job_runner_final.py`. |
| `cp2kvasp_example.csv` | Example mixed-code job queue for `cp2k_vasp_job_runner.py`. |
| `CODE_BREAKDOWN.md` | Detailed walkthrough of how the scripts work internally. |
| `Notify_Config.md` | Setup instructions for each notification channel. |
| `Usage_Job_runners.md` | Older usage notes (written for an earlier version of the runner — see below). |
| `enviroment.yml` / `enviroment_no_build.yml` | Conda environment specs. |
| `requirements.txt` | Pip freeze of the working environment. |

> **Note:** `Usage_Job_runners.md` predates `cp2k_job_runner_final.py` and references an older CLI (positional `results.csv` arg, `--create-example` flag). The instructions below reflect the current script.

## Features

- **Sequential job queue from CSV** — one job at a time, respecting per-job core counts and wall-time limits.
- **Crash protection** — a failure in one job (bad input, CP2K error, walltime timeout) is caught, logged, and the queue continues to the next job. An unhandled crash still saves partial results and sends a notification with the full traceback before exiting.
- **Live CSV reload** — jobs can be appended to the input CSV while the queue is running (disable with `--no-live-reload`).
- **Multi-channel notifications** — HTML email (with embedded energy plots), Slack, Microsoft Teams, and LINE Works webhooks, each independently toggleable in `notification_config.json`.
- **Automatic post-processing per job**:
  - Parses CP2K output for total energy, SCF convergence, forces, and wall time.
  - Parses `PROJECT_NAME-pos-1.xyz` trajectories and generates an energy-vs-step plot.
  - Exports the final structure to CIF using cell parameters read from the input file.
- **Results log** — every job's outcome is appended to a results CSV (status, timings, energies, convergence, paths to plot/CIF).

## Requirements

- CP2K (OpenMP build, e.g. `cp2k.ssmp`) on `PATH`, or the full path passed via `--executable`
- Python packages: `pandas`, `matplotlib`, `numpy`, `requests` (see `requirements.txt` / `enviroment.yml`)

```bash
conda env create -f enviroment.yml
# or
pip install -r requirements.txt
```

> `requirements.txt` was generated from a conda environment and includes some conda-local file paths that won't resolve on other machines. Prefer `enviroment.yml`, or regenerate `requirements.txt` with `pip freeze` in a clean venv if you need a portable pip-only install.

## Usage

### 1. Build a job queue CSV

Required columns: `job_file`, `num_cores`. Optional: `job_name`, `wall_time_hours`.

```csv
job_name,job_file,num_cores,wall_time_hours
water_opt,/path/to/water_opt.inp,4,2
graphene_scf,/path/to/graphene.inp,8,4
```

### 2. (Optional) Set up notifications

```bash
python cp2k_job_runner_final.py --create-notify-config
```

This writes a `notification_config.json` template. Fill in whichever channels you want (`enabled: true`) and either put credentials directly in the file or set them via environment variables (e.g. `NOTIFY_SENDER_PASSWORD`) — don't commit real credentials to the repo.

### 3. Run the queue

```bash
python cp2k_job_runner_final.py my_jobs.csv \
    --output results.csv \
    --executable cp2k.ssmp \
    --walltime 12 \
    --notify-config notification_config.json
```

**CLI options:**

| Flag | Description | Default |
|---|---|---|
| `--output <file>` | Output results CSV | `cp2k_results.csv` |
| `--executable <path>` | CP2K binary | `cp2k.ssmp` |
| `--walltime <hours>` | Default per-job wall time limit (overridden by CSV column if present) | `12.0` |
| `--notify-config <file>` | Path to notification config | none |
| `--no-live-reload` | Disable re-reading the input CSV for newly appended jobs | live reload on |
| `--create-notify-config` | Write a template `notification_config.json` and exit | — |

### 4. Check results

Each row of the output CSV is one job: `status` (`SUCCESS` / `FAILED` / `TIMEOUT` / `ERROR`), timings, `total_energy`, `scf_converged`, `num_scf_steps`, and paths to the generated energy plot and CIF file (if a trajectory was found).

## Known limitations

- **No resource-aware scheduling** — `num_cores` per job is taken as given; nothing checks that it fits available RAM/CPU, so it's still on you to size jobs sensibly for large (400+ atom) configurations.
- **Sequential only** — jobs run one at a time, no parallel job execution.
- **Single-file scripts** — `cp2k_job_runner_final.py` bundles structure handling, plotting, notifications, and the runner itself in one ~2,300-line file. Fine for a personal tool, would benefit from splitting into modules if this grows further.
- `cp2k_vasp_job_runner.py` duplicates a fair amount of the notification/plotting logic from the CP2K-only script rather than importing shared code.

## License

No license file included yet — add one if you intend others to reuse this.

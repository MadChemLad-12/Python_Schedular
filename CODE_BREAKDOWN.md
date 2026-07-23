# CP2K Job Runner - Full Code Breakdown

A complete explanation of how the script works, what every section does,
and definitions for every keyword and concept used.

---

## Table of Contents

1. High-Level Overview
2. Imports Section (Lines 1–26)
3. Class: StructureHandler (Lines 29–260)
4. Class: EnergyPlotter (Lines 263–329)
5. Class: Notifier (Lines 332–~1800)
6. Class: CP2KJobRunner (Lines ~1800–2180)
7. Helper Functions & Entry Point (Lines 2183–2273)
8. Keyword Glossary
9. Data Flow Diagram

---

## 1. High-Level Overview

The script is split into four **classes**, each responsible for one job:

```
┌─────────────────────────────────────────────────────────┐
│                   cp2k_job_runner_final.py               │
├────────────────┬────────────────┬────────────────────────┤
│StructureHandler│ EnergyPlotter  │       Notifier          │
│                │                │                        │
│ Reads .inp     │ Reads          │ Sends Slack/Email/      │
│ files for cell │ pos-1.xyz and  │ Teams notifications    │
│ parameters and │ draws the      │ for completions and    │
│ project name   │ energy plot    │ crashes                │
│                │                │                        │
│ Reads pos-1.xyz│ Saves plot as  │ Reads config from      │
│ for trajectory │ PNG on disk    │ notification_config    │
│                │ and in memory  │ .json                  │
│ Writes the     │ for email      │                        │
│ final .cif     │ embedding      │                        │
│ structure file │                │                        │
└────────────────┴────────────────┴────────────────────────┘
                          │
                          ▼
            ┌─────────────────────────┐
            │      CP2KJobRunner      │
            │                         │
            │ Reads your CSV job list │
            │ Runs each job with CP2K │
            │ Enforces wall time limit│
            │ Calls other 3 classes   │
            │ Saves results to CSV    │
            │ Catches crashes         │
            └─────────────────────────┘
```

The execution order for each job is:

```
Read CSV → Run CP2K → Parse .out → Parse pos-1.xyz → Plot → CIF → Notify → Save CSV → Next Job
```

---

## 2. Imports Section (Lines 1–26)

```python
#!/usr/bin/env python3
```
**Shebang line.** Tells the operating system to run this file using Python 3.
Makes the file directly executable on Linux/Mac (`./script.py`) without
needing to type `python` first.

---

```python
import pandas as pd
```
**pandas** — A data analysis library. Used here to read your input CSV
(`pd.read_csv`) and write the results CSV (`df.to_csv`). The alias `pd`
is conventional shorthand.

---

```python
import subprocess
```
**subprocess** — Python's built-in module for running external programs.
This is how the script actually *launches CP2K*. Without this, Python
cannot run another program. The key function used is `subprocess.run()`.

---

```python
import os
```
**os** — Operating system interface. Used to check if files exist
(`os.path.exists`), read environment variables (`os.environ.get`), and
copy the system environment to pass to CP2K.

---

```python
import sys
```
**sys** — System-level utilities. Used to read command-line arguments
(`sys.argv`) and to exit the script cleanly (`sys.exit`).

---

```python
import time
```
**time** — Used to measure how long each job runs. `time.time()` returns
the current time in seconds since 1970 (Unix epoch). Subtracting start
from end gives elapsed seconds.

---

```python
from datetime import datetime
```
**datetime** — Formats timestamps for the results CSV and notifications,
e.g. `2024-02-16 14:30:15`.

---

```python
from pathlib import Path
```
**pathlib.Path** — A modern way to work with file paths in Python. More
readable than string concatenation. For example:
`Path('/data/sims') / 'protein_01.inp'` produces `/data/sims/protein_01.inp`.

---

```python
import re
```
**re** — Regular expressions. Used extensively to extract data from text
files by pattern matching. For example, finding `E = -1245.678` in a
line of text. Every `re.search(r'...', text)` call is searching for a
pattern.

---

```python
import json
```
**json** — Reads and writes JSON files. Used to load your
`notification_config.json` configuration file.

---

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
```
**Email libraries** — Python's built-in email sending tools.
- `smtplib` connects to the mail server (SMTP protocol)
- `MIMEText` creates the text/HTML body of the email
- `MIMEMultipart` allows the email to have multiple parts (HTML body +
  image attachment)
- `MIMEImage` encodes the plot as an inline image inside the email

---

```python
import requests
```
**requests** — The most popular Python library for making HTTP web
requests. Used to POST messages to Slack, Teams, and LINE Work webhooks.
A **webhook** is just a URL that accepts a POST request with JSON data
and does something with it (like posting a message to a channel).

---

```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
```
**matplotlib** — Python's primary plotting library.
`matplotlib.use('Agg')` is critical — it switches matplotlib to a
**non-interactive backend** called Agg (Anti-Grain Geometry). Without
this, matplotlib tries to open a GUI window, which fails on a server
with no display. `Agg` renders plots entirely in memory to PNG files
instead.

---

```python
import numpy as np
```
**numpy** — Numerical Python. Used to convert energy/step lists to arrays
for efficient mathematical operations. The alias `np` is conventional.

---

```python
from io import BytesIO
```
**BytesIO** — An in-memory binary file object. The plot is saved into a
`BytesIO` buffer (not a real file) so it can be attached to an email
without needing a temporary file on disk. Think of it as a file that
lives entirely in RAM.

---

```python
import base64
```
**base64** — Encodes binary data (like images) as plain text characters.
Imported but the main image-in-email embedding now uses `MIMEImage`
directly. Kept for compatibility.

---

## 3. Class: StructureHandler (Lines 29–260)

This class handles everything related to reading and writing crystal
structure data. It has no state of its own — all four methods are
decorated with `@staticmethod`, meaning you call them as
`StructureHandler.method()` without creating an instance.

### What is `@staticmethod`?

A regular method needs an *instance* of the class first:
```python
handler = StructureHandler()   # Create instance
handler.parse_xyz_trajectory() # Call method on instance
```
A static method belongs to the class itself, not any instance:
```python
StructureHandler.parse_xyz_trajectory()  # No instance needed
```
Used here because these are utility functions that don't need to
remember anything between calls.

---

### Method: `get_project_name` (Lines 33–63)

**Purpose:** Reads your CP2K input `.inp` file and finds the line that
says `PROJECT bot_wet0.75` (or `PROJECT_NAME bot_wet0.75`). Returns
that name as a string.

**Why it matters:** CP2K names all its output files using the PROJECT
name, not the input filename. If your input file is called `Ptw0.375.inp`
but inside it says `PROJECT bot_wet0.75`, then CP2K creates:
- `bot_wet0.75-pos-1.xyz`  ← trajectory
- `bot_wet0.75-frc-1.xyz`  ← forces
- `bot_wet0.75.restart`    ← restart file

Without this function, the script would look for `Ptw0.375-pos-1.xyz`
and never find the trajectory.

**Key line:**
```python
project_match = re.search(
    r'PROJECT(?:_NAME)?\s+(\S+)',
    content,
    re.IGNORECASE
)
```
**Breaking down the regex:**
- `PROJECT` — literal text to find
- `(?:_NAME)?` — optionally also match `_NAME` (the `?:` means don't
  capture this group, just match it; the `?` at the end means 0 or 1
  times)
- `\s+` — one or more whitespace characters (space or tab)
- `(\S+)` — capture one or more non-whitespace characters (the actual
  project name)
- `re.IGNORECASE` — match regardless of uppercase/lowercase

---

### Method: `parse_xyz_trajectory` (Lines 66–151)

**Purpose:** Reads the entire `pos-1.xyz` trajectory file and extracts
every energy value and every set of atomic coordinates at each geometry
step.

**XYZ file format** — The file repeats this block for every step:
```
64                          ← Line 1: number of atoms
 i = 10, E = -1245.6789    ← Line 2: comment with step and energy
C   5.427   5.427   5.427  ← Lines 3 to N+2: element + X Y Z coordinates
C   6.523   6.523   6.523
H   4.331   4.331   4.331
...                         ← 64 atom lines total
64                          ← Next block starts
 i = 11, E = -1245.6891
...
```

**How it parses this:**
```python
i = 0                          # Line counter
while i < len(lines):
    n_atoms = int(lines[i])    # Read atom count from line 1
    comment = lines[i + 1]     # Read comment from line 2
    # Extract energy from comment using regex
    # Read n_atoms lines of coordinates
    i += n_atoms + 2           # Jump to start of next block
```
The `i += n_atoms + 2` is the key — it skips exactly one complete block
(2 header lines + n_atoms coordinate lines) each iteration.

**Returns a dictionary with:**
- `energies` — list like `[-1245.678, -1245.689, -1245.691, ...]`
- `steps` — list like `[10, 11, 12, ...]`
- `structures` — list of lists, each inner list being all atoms at that
  step: `[{'element': 'C', 'x': 5.427, 'y': 5.427, 'z': 5.427}, ...]`
- `cell` — None (not extracted from XYZ, read from input file instead)

---

### Method: `parse_cell_from_input` (Lines 153–211)

**Purpose:** Reads your CP2K `.inp` file and extracts the unit cell
dimensions (a, b, c in Ångströms) and angles (alpha, beta, gamma in
degrees).

**Why needed for CIF:** A CIF file requires the unit cell to place atoms
correctly in space. The XYZ file only gives Cartesian coordinates; the
cell information is needed to convert those to fractional coordinates.

**Two formats supported:**

Format 1 — Individual A, B, C keywords inside a `&CELL` block:
```
&CELL
  A 10.855
  B 10.855
  C 10.855
  ALPHA 90.0
  BETA  90.0
  GAMMA 90.0
&END CELL
```

Format 2 — ABC shorthand on one line:
```
&CELL
  ABC 10.855 10.855 10.855
&END CELL
```

If angles (ALPHA, BETA, GAMMA) are not found, they default to 90.0°,
which assumes an **orthogonal** (cubic/tetragonal/orthorhombic) cell.

**`re.DOTALL`** — A regex flag that makes `.` match newline characters
too, allowing the pattern to span multiple lines of the file.

---

### Method: `write_cif` (Lines 213–260)

**Purpose:** Takes a structure (list of atoms with coordinates) and cell
parameters, and writes a standard `.cif` file.

**CIF format (Crystallographic Information File):**
```cif
data_optimised_structure          ← Block name

_cell_length_a    10.855200       ← Cell edge a in Ångströms
_cell_length_b    10.855200       ← Cell edge b
_cell_length_c    10.855200       ← Cell edge c
_cell_angle_alpha 90.000000       ← Angle between b and c axes
_cell_angle_beta  90.000000       ← Angle between a and c axes
_cell_angle_gamma 90.000000       ← Angle between a and b axes
_symmetry_space_group_name_H-M 'P 1'   ← Space group (P 1 = no symmetry)
_symmetry_Int_Tables_number    1        ← International Tables number

loop_                             ← Start of repeating data table
_atom_site_label                  ← Column: unique atom label
_atom_site_type_symbol            ← Column: element symbol
_atom_site_fract_x                ← Column: fractional x coordinate
_atom_site_fract_y
_atom_site_fract_z

C1       C    0.12345678  0.23456789  0.34567890
C2       C    0.23456789  0.34567890  0.45678901
H1       H    0.11111111  0.22222222  0.33333333
```

**Cartesian → Fractional coordinate conversion:**
```python
frac_x = atom['x'] / cell['a']   # e.g. 1.23 Å / 10.855 Å = 0.1133
frac_y = atom['y'] / cell['b']
frac_z = atom['z'] / cell['c']
```
This simple division only works for orthogonal cells. For non-orthogonal
cells (alpha/beta/gamma ≠ 90°) a full matrix transformation would be
needed.

**`P 1` space group** — This is the triclinic space group with no
symmetry. It means "place all atoms explicitly, don't apply any
symmetry operations." Always safe to use when exporting from a
simulation that didn't impose symmetry.

---

## 4. Class: EnergyPlotter (Lines 263–329)

This class has one job: take a list of energies and steps and produce a
publication-quality PNG plot.

### Method: `create_energy_plot` (Lines 267–329)

**Purpose:** Creates the energy vs step graph, saves it to disk, and
also returns it as an in-memory PNG for email embedding.

**Step by step:**

```python
plt.figure(figsize=(10, 6), dpi=100)
```
Creates a new figure. `figsize=(10, 6)` means 10 inches wide, 6 inches
tall. `dpi=100` means 100 dots per inch, giving a 1000×600 pixel image.

```python
steps = np.array(steps)
energies = np.array(energies)
```
Converts Python lists to numpy arrays. Required for matplotlib to plot
them and for numpy math operations.

```python
plt.plot(steps, energies, 'b-', linewidth=2, label='Energy')
```
Plots the line. `'b-'` means blue (`b`) solid line (`-`). `linewidth=2`
makes it 2 points thick. `label='Energy'` is what appears in the legend.

```python
plt.text(0.02, 0.98, stats_text,
         transform=plt.gca().transAxes, ...)
```
Places the statistics box. `transform=plt.gca().transAxes` means the
coordinates (0.02, 0.98) are in **axes fraction** (0=left/bottom,
1=right/top), not in data units. So (0.02, 0.98) = 2% from left, 98%
from top, regardless of what the actual energy values are.

```python
img_buffer = BytesIO()
plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
img_buffer.seek(0)
```
Saves the plot into a `BytesIO` buffer in memory as a PNG. `seek(0)` 
rewinds the buffer to the beginning, ready to be read. This is then
passed to the email sender as the inline image.

```python
plt.close()
```
**Critical.** Closes the figure and frees its memory. Without this,
each plot would accumulate in memory. After 15 jobs this would be a
significant memory leak.

---

## 5. Class: Notifier (Lines 332–~1800)

The largest class. Handles all communication: reading config, building
messages, and dispatching to each platform.

### `__init__` (Lines 335–346)

The **constructor** — runs automatically when you create a `Notifier`
object. Sets all platform flags to `False` by default, then loads
whichever config source is available.

```python
self.email_enabled = False
self.slack_enabled = False
self.teams_enabled = False
self.linework_enabled = False
```
These boolean flags act as switches. Every send method checks its flag
first: `if not self.slack_enabled: return False`. This means you can
safely have all four methods called without any enabled — they just
silently return.

---

### `load_config` (Lines 348–384)

Reads `notification_config.json` using `json.load()`, then for each
platform checks if `"enabled": true`. If so, it stores the credentials
as instance variables (`self.smtp_server = ...`) so other methods can
use them.

**`config.get('email', {})`** — The `.get(key, default)` pattern
returns the value for `key` if it exists, or the `default` if not. The
`{}` (empty dict) means if there's no `email` section at all, it
returns an empty dict, and the subsequent `.get('enabled', False)` also
safely returns `False`. This prevents a crash if someone leaves a
section out of the config.

---

### `load_from_env` (Lines 386–411)

Alternative to the config file. Reads the same settings from environment
variables instead. For example:
```bash
export NOTIFY_SLACK_ENABLED=true
export NOTIFY_SLACK_WEBHOOK="https://hooks.slack.com/..."
```

**`os.environ.get('NOTIFY_SLACK_ENABLED', '')`** — Returns the
environment variable value or an empty string if not set. The `.lower()`
converts it to lowercase so `TRUE`, `True`, and `true` all work.

---

### `create_html_email_body` (Lines 413–~700)

Builds the entire HTML email as a Python string using f-strings. The
email is structured like a webpage:

```
<html>
  <head><style> ... CSS styling ... </style></head>
  <body>
    <div class="header">  ← Coloured banner with job name
    <div class="section"> ← Energy plot (if available)
    <div class="section"> ← Job information table
    <div class="section"> ← Timing table
    <div class="section"> ← Energy & convergence table
    <div class="section"> ← Error box (if failed)
    <div class="footer">  ← Timestamp
  </body>
</html>
```

**`{{` and `}}`** — In Python f-strings, single `{` and `}` are used
for variable substitution: `f"Hello {name}"`. To include a literal `{`
or `}` in the output (needed for CSS), you must double them: `{{` → `{`
and `}}` → `}`.

**`cid:energy_plot`** — Content ID. In MIME email format, inline images
are referenced not by a file path but by a content ID. The image is
attached to the email with `Content-ID: <energy_plot>`, and the HTML
references it with `src="cid:energy_plot"`. This is how the plot appears
inside the email body rather than as a download attachment.

**Status colours:**
- `#28a745` — Bootstrap green (SUCCESS)
- `#ffc107` — Bootstrap amber/yellow (TIMEOUT)
- `#dc3545` — Bootstrap red (FAILED)
- `#6c757d` — Bootstrap grey (ERROR)

---

### `send_email` (Lines ~700–750)

Constructs and sends the email using Python's built-in SMTP library.

```python
msg = MIMEMultipart('related')
```
`'related'` is the MIME type that allows inline images. The structure is:
```
MIMEMultipart('related')          ← Outer container (handles inline images)
├── MIMEMultipart('alternative')  ← Inner container (handles text vs HTML)
│   ├── MIMEText(..., 'plain')    ← Plain text fallback
│   └── MIMEText(..., 'html')     ← HTML version (preferred)
└── MIMEImage(img_data)           ← Inline image (the plot)
```
Email clients try the *last* part of `alternative` first (HTML), falling
back to plain text if HTML isn't supported.

```python
with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
    server.starttls()
    server.login(self.sender_email, self.sender_password)
    server.send_message(msg)
```
**SMTP** — Simple Mail Transfer Protocol. The sequence is:
1. Connect to server on port 587
2. `starttls()` — upgrade connection to encrypted TLS (Transport Layer
   Security). Port 587 is specifically the "submission with STARTTLS"
   port.
3. Login with credentials
4. Send the message
5. Connection automatically closed by the `with` block

---

### `send_slack` (Lines ~800–950)

Sends a rich-formatted message to Slack using the **Incoming Webhooks**
API. No authentication — the webhook URL itself is the secret.

**Slack Block Kit** — Slack's structured message format. Instead of
plain text, you send a JSON array of "blocks", each being a visual
component:

```python
blocks = [
    {
        "type": "header",        # Bold title bar
        "text": {"type": "plain_text", "text": "✅ Job SUCCESS"}
    },
    {
        "type": "section",       # Content area
        "fields": [              # Two-column layout
            {"type": "mrkdwn", "text": "*Status:*\nSUCCESS"},
            {"type": "mrkdwn", "text": "*Time:*\n18.4 hours"}
        ]
    }
]
```

**`mrkdwn`** — Slack's version of Markdown. `*bold*`, `_italic_`,
`` `code` ``, ` ```code block``` `.

**`"attachments": [{"color": "good"}]`** — The coloured sidebar on the
left of a Slack message. `"good"` = green, `"warning"` = yellow,
`"danger"` = red.

```python
response = requests.post(self.slack_webhook, json=payload)
return response.status_code == 200
```
`requests.post()` sends an HTTP POST request. The `json=payload`
parameter automatically serialises the Python dict to JSON and sets the
`Content-Type: application/json` header. Status code `200` means
success.

---

### `notify_job_complete` (Lines ~950–990)

The **dispatcher** — called after every job finishes. Checks each
platform flag and calls the appropriate send method.

```python
if self.slack_enabled:
    self.send_slack(result)
    print(f"  💬 Slack notification sent")
```

It also receives `plot_img` (the BytesIO buffer from the plotter) and
passes it through to `send_email`, which attaches it as an inline image.

---

### `notify_crash` (Lines ~1000–1150)

The emergency notification method. Called from the crash handler in
`run_all_jobs`. Deliberately designed to be as robust as possible:

- Uses `timeout=10` on HTTP requests so a slow network won't cause it
  to hang indefinitely
- Wraps each platform in its own separate `try/except` so if Slack
  fails it still tries email
- Keeps the Slack message under Slack's 3000-character block limit by
  truncating the traceback: `traceback_info[:1000]`

---

## 6. Class: CP2KJobRunner (Lines ~1800–2180)

The main controller. Reads your job list, runs each job, and
orchestrates all the other classes.

### `__init__` (Constructor)

```python
def __init__(self, input_csv, output_csv, cp2k_executable,
             wall_time_hours, notify_config, notify_mode):
```

**Parameters stored as instance variables:**
- `self.input_csv` — path to your jobs CSV
- `self.output_csv` — path to write results CSV
- `self.cp2k_executable` — e.g. `"cp2k.ssmp"` or `"/path/to/cp2k"`
- `self.wall_time_hours` — default wall time for all jobs
- `self.wall_time_seconds` — same, converted to seconds for
  `subprocess.run(timeout=...)`

**Creates the Notifier:**
```python
self.notifier = Notifier(notify_config, notify_mode)
```
The Notifier is created once and reused for all 15 jobs.

**`_verify_cp2k()`** — Immediately checks that the CP2K binary exists
and is callable. Runs `cp2k.ssmp --version` and captures the output.
If CP2K isn't found, the script exits immediately with a clear error
rather than silently failing 8 hours into the first job.

---

### `read_jobs` (Lines ~1850–1880)

```python
df = pd.read_csv(self.input_csv)
```
Reads the CSV into a pandas DataFrame — a table where each row is a job
and each column is a parameter. The required columns are validated:

```python
required_cols = ['job_file', 'num_cores']
for col in required_cols:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")
```

If `wall_time_hours` column is absent, it's filled with the global
default:
```python
if 'wall_time_hours' not in df.columns:
    df['wall_time_hours'] = self.wall_time_hours
```

---

### `parse_cp2k_output` (Lines ~1880–1960)

Reads the `.out` file (CP2K's main output) and extracts:

**Energy:**
```python
energy_matches = re.findall(
    r'ENERGY\| Total FORCE_EVAL.*?:\s+([-\d.]+)', content
)
```
`re.findall` returns *all* matches. The `[-1]` takes the last one
because CP2K prints this line once per geometry step, and the final one
is the converged result.

**SCF convergence:**
```python
if "PROGRAM ENDED AT" in content:
    results['scf_converged'] = True
```
CP2K only prints `PROGRAM ENDED AT` if the calculation finished
successfully. A crash or non-convergence won't have this line.

**Forces:**
```python
re.findall(r'SUM OF ATOMIC FORCES\s+([-\d.E+]+)', content)
```
The `[-\d.E+]+` pattern matches scientific notation like `1.23456E-06`.

---

### `process_trajectory_and_structure` (Lines ~1960–2050)

The coordinator that calls both `StructureHandler` and `EnergyPlotter`
after a job finishes.

**File search logic:**
```python
project_name = StructureHandler.get_project_name(input_file)

# Try PROJECT_NAME-pos-1.xyz first
xyz_file = job_path / f"{project_name}-pos-1.xyz"

# If not found, try fallbacks
if not xyz_file.exists():
    alternatives = [
        job_path / f"{job_name}-pos-1.xyz",
        job_path / "pos-1.xyz",
    ]
```
This three-tier search solves the PROJECT_NAME vs job_name mismatch.

**Output files use `job_name` for consistency:**
```python
plot_file = job_path / f"{job_name}_energy_plot.png"
cif_file  = job_path / f"{job_name}_optimised_structure.cif"
```
Even though the trajectory was found under `bot_wet0.75-pos-1.xyz`, the
outputs are named after your job label (`Ptw0.375`), keeping your
directory organised by your naming scheme.

---

### `run_cp2k_job` (Lines ~2050–2000)

The core function. Runs a single CP2K calculation.

```python
cmd = [
    self.cp2k_executable,   # e.g. 'cp2k.ssmp'
    '-i', str(job_file),    # input file flag
    '-o', str(output_file)  # output file flag
]
```
This is equivalent to typing in the terminal:
```bash
cp2k.ssmp -i protein_01.inp -o protein_01.out
```

**Environment setup:**
```python
env = os.environ.copy()       # Copy current environment
env['OMP_NUM_THREADS'] = str(num_cores)  # Set thread count
env['OMP_PROC_BIND'] = 'close'           # Bind threads to nearby CPUs
env['OMP_PLACES'] = 'cores'              # Thread placement policy
```
`os.environ.copy()` is important — it takes the full current environment
(PATH, LD_LIBRARY_PATH, etc.) so CP2K can find all its libraries, then
adds the OpenMP variables on top.

**`OMP_PROC_BIND = 'close'`** — Tells the OS to keep OpenMP threads on
CPU cores that are physically close to each other (same socket/NUMA
node). Reduces memory latency, especially on multi-socket machines.

**`OMP_PLACES = 'cores'`** — Each OpenMP thread gets its own physical
core. Without this, two threads might share a hyperthreaded core, which
is slower for compute-intensive code like CP2K.

**Running the job:**
```python
result = subprocess.run(
    cmd,
    env=env,
    capture_output=True,   # Don't print CP2K output to terminal
    text=True,             # Decode stdout/stderr as text strings
    timeout=wall_time_seconds,  # Kill after this many seconds
    cwd=str(job_path)      # Run from the job's directory
)
```
`cwd=str(job_path)` is important because CP2K writes all output files
relative to its working directory.

**Wall time enforcement:**
```python
except subprocess.TimeoutExpired:
    # CP2K is automatically killed when timeout is exceeded
    # We land here and record status = 'TIMEOUT'
```
When the timeout fires, Python sends `SIGKILL` to the CP2K process,
terminating it immediately. The script then processes whatever partial
output exists in the `.out` and `pos-1.xyz` files — so you still get a
partial energy plot even from a timed-out job.

---

### `run_all_jobs` (Lines ~2000–2143)

The main loop with three-layer error protection:

```python
try:                          # ← Outer: catch fatal crashes
    while job_idx < total:
        try:                  # ← Inner: catch per-job errors
            result = self.run_cp2k_job(...)
        except Exception as job_error:
            # Log job error, continue to next job
            
except KeyboardInterrupt:     # ← Ctrl+C handler
    notify_crash(...)
    raise

except Exception as e:        # ← Fatal crash handler
    notify_crash(...)
    raise
```

**`live_reload` logic:**
```python
if live_reload:
    jobs_df = self.read_jobs()  # Re-read CSV before each job
```
This re-reads the entire CSV at the start of each job. If you edit the
CSV while the script is running (e.g., change wall_time_hours for
job 8 while job 7 is running), the change takes effect when job 8
starts. It has no effect on the currently running job.

**`job_idx` counter:** An integer that starts at 0 and increments by 1
after each job regardless of whether it succeeded, failed, or timed out.
This is how the script always moves forward through the queue.

---

### `save_results` (Lines 2177–2180)

```python
results_df = pd.DataFrame(self.results)
results_df.to_csv(self.output_csv, index=False)
```
Called after *every* job. `self.results` is a list of dictionaries.
`pd.DataFrame(self.results)` converts it to a table where each dict
becomes a row. `index=False` suppresses the auto-generated row numbers
(0, 1, 2...) that pandas would otherwise add as the first column.

This incremental save means if the script crashes after job 7, jobs 1–7
are safely in the CSV.

---

## 7. Helper Functions & Entry Point (Lines 2183–2273)

### `create_example_notification_config`

Creates a template `notification_config.json` with all platforms shown
but all set to `false`. Run with:
```bash
python cp2k_job_runner_final.py --create-notify-config
```

### `if __name__ == "__main__":` block

**What this means:** Python sets the special variable `__name__` to
`"__main__"` when the script is run directly. If another script were to
`import cp2k_job_runner_final`, this block would NOT run. It's a Python
convention that separates executable code from importable code.

**Argument parsing:**
```python
i = 2
while i < len(sys.argv):
    arg = sys.argv[i]
    if arg == '--walltime' and i+1 < len(sys.argv):
        wall_time_hours = float(sys.argv[i+1])
        i += 2          # Skip both '--walltime' and the value
    ...
```
`sys.argv` is a list of everything you typed on the command line:
```
sys.argv[0] = 'cp2k_job_runner_final.py'
sys.argv[1] = 'jobs.csv'
sys.argv[2] = '--walltime'
sys.argv[3] = '24'
```
The parser walks through the list, recognises flags, and reads the
value that follows each flag.

---

## 8. Keyword Glossary

**`class`** — A blueprint for creating objects. Groups related data
(variables) and functions (methods) together. The four classes in this
script each handle one area of responsibility.

**`def`** — Defines a function or method.

**`self`** — Inside a class method, `self` refers to the specific
instance of that class. `self.slack_enabled` is the `slack_enabled`
variable belonging to this particular `Notifier` object.

**`@staticmethod`** — Decorator that marks a method as not needing
`self`. Used for utility functions that don't read or write any instance
variables.

**`try / except`** — Error handling. Code in `try` is attempted. If it
raises an exception, execution jumps to the matching `except` block
instead of crashing. `except Exception as e` catches all standard
exceptions and gives you the error object as `e`.

**`raise`** — Re-raises the current exception after handling it. Used
in the crash handler so the error still propagates after the
notification is sent, giving you the full traceback in the terminal.

**`f-string`** — `f"text {variable} text"` — Python's string
interpolation syntax. The expression inside `{}` is evaluated and
inserted into the string.

**`dict`** — Dictionary. A key-value store: `{'status': 'SUCCESS',
'energy': -1245.678}`. Accessed with `d['status']` or safely with
`d.get('status', 'N/A')`.

**`list`** — An ordered, mutable sequence: `[1, 2, 3]`. Used for storing
energies, steps, and structures from the trajectory.

**`None`** — Python's null value. Used as a default when a value hasn't
been set yet. `if result.get('total_energy') is not None:` checks
whether an energy was successfully parsed.

**`regex (re)`** — Regular expressions. A mini-language for pattern
matching in text. `\d+` matches digits, `[-\d.]+` matches a number that
can be negative, `\s+` matches whitespace, `()` captures a group.

**`subprocess`** — Python's way of running external programs. Here used
exclusively to launch CP2K.

**`timeout`** — The maximum number of seconds `subprocess.run()` will
wait before forcibly killing the child process. This is the mechanism
behind the wall time limit feature.

**`webhook`** — A URL that accepts HTTP POST requests. Slack, Teams, and
LINE Work all expose webhooks that, when posted to with the right JSON
payload, create messages in your channels. No ongoing connection or
authentication is maintained — it's a single fire-and-forget HTTP
request each time.

**`SMTP`** — Simple Mail Transfer Protocol. The standard protocol for
sending email. Port 587 with STARTTLS is the modern standard for
authenticated mail submission.

**`MIME`** — Multipurpose Internet Mail Extensions. The standard that
allows emails to contain HTML, images, attachments, etc. rather than
just plain text.

**`BytesIO`** — An in-memory file-like object that stores bytes.
Allows the plot to be saved to "a file" in RAM, then read from RAM
directly into the email, without ever touching the filesystem for the
email-embed copy.

**`OMP_NUM_THREADS`** — Environment variable that tells OpenMP (the
parallelism framework used by CP2K's shared-memory mode) how many CPU
threads to use for a calculation.

**`OpenMP`** — A standard for parallel programming on a single computer.
`cp2k.ssmp` (the binary name) stands for "single-process, shared-memory
parallel" — i.e., one Python process, multiple OpenMP threads.

**`CIF`** — Crystallographic Information File. The standard file format
for crystal structures. Readable by VESTA, Mercury, PyMOL, and most
other crystallography software.

**`fractional coordinates`** — Atom positions expressed as fractions of
the unit cell edge lengths (0.0 to 1.0), rather than absolute Ångström
distances. Required by the CIF format.

**`Hartree (Ha)`** — The atomic unit of energy. 1 Hartree = 27.211 eV =
627.5 kcal/mol. CP2K reports energies in Hartree by default.

**`SCF`** — Self-Consistent Field. The iterative procedure used in DFT
to find the electron density that minimises the energy. "SCF converged"
means the calculation found a stable solution. "SCF not converged" means
it ran out of iterations before stabilising.

**`pos-1.xyz`** — CP2K's trajectory output file. The `-1` indicates it
is the first restart of the trajectory (CP2K restarts are numbered). It
contains all atomic positions at each geometry optimisation or MD step.

**`wall time`** — Real-world clock time elapsed. Distinct from CPU time
(which accumulates across all cores). An 8-hour job on 16 cores has
8 hours of wall time but up to 128 hours of CPU time.

**`live reload`** — The feature that re-reads the input CSV before each
job starts. Allows you to change settings for upcoming jobs while the
script is running.

**`DataFrame`** — pandas' core data structure. A 2D table with labelled
rows and columns. Here, each row is one job's results, and each column
is one metric (status, energy, elapsed time, etc.).

---

## 9. Data Flow Diagram

```
Your terminal command:
python cp2k_job_runner_final.py jobs.csv --notify-config config.json
        │
        ▼
┌────────────────────────────────────┐
│ Parse command-line arguments       │
│ Create CP2KJobRunner instance      │
│ Create Notifier instance           │
│   └─ Load config.json             │
│   └─ Set slack_enabled = True      │
└────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────┐
│ run_all_jobs()                     │
│   read_jobs() → jobs DataFrame     │
│   ┌──────────────────────────────┐ │
│   │ For each row in DataFrame:   │ │
│   │                              │ │
│   │  run_cp2k_job()              │ │
│   │   ├─ Build command           │ │
│   │   ├─ Set OMP env vars        │ │
│   │   ├─ subprocess.run(CP2K)    │ │
│   │   │   └─ Waits up to N hours │ │
│   │   │   └─ CP2K writes:        │ │
│   │   │       ├─ job.out         │ │
│   │   │       └─ proj-pos-1.xyz  │ │
│   │   ├─ parse_cp2k_output()     │ │
│   │   │   └─ Read job.out        │ │
│   │   │   └─ Extract energy,     │ │
│   │   │       SCF, forces        │ │
│   │   └─ process_trajectory()    │ │
│   │       ├─ get_project_name()  │ │
│   │       ├─ parse_xyz_traj()    │ │
│   │       │   └─ All energies    │ │
│   │       │   └─ Final structure │ │
│   │       ├─ create_energy_plot()│ │
│   │       │   └─ Save PNG file   │ │
│   │       │   └─ Return BytesIO  │ │
│   │       ├─ parse_cell()        │ │
│   │       └─ write_cif()         │ │
│   │           └─ Save CIF file   │ │
│   │                              │ │
│   │  notify_job_complete()       │ │
│   │   ├─ create_html_email()     │ │
│   │   ├─ send_email() + plot img │ │
│   │   └─ send_slack()            │ │
│   │                              │ │
│   │  save_results()              │ │
│   │   └─ Append row to CSV       │ │
│   │                              │ │
│   └──────────────────────────────┘ │
│                                    │
│   If crash: notify_crash()         │
│     └─ send_slack(full traceback)  │
│                                    │
│   notify_queue_complete()          │
│     └─ send_slack(summary)         │
└────────────────────────────────────┘

Output files created per job:
├── job_name.out                  (CP2K, always)
├── project-pos-1.xyz             (CP2K, if enabled in input)
├── job_name_energy_plot.png      (this script)
├── job_name_optimised_structure.cif  (this script)
└── cp2k_results.csv              (this script, one row added per job)
```

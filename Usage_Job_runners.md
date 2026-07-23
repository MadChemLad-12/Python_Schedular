# CP2K Job Runner - Usage Instructions

## Quick Start

### 1. Activate Your Environment
```bash
conda activate mpi-sim
```

### 2. Set OpenMP Threads
Since your CP2K is built without MPI, set the number of threads:
```bash
export OMP_NUM_THREADS=8  # Use all 8 cores
```

### 3. Create Job Queue CSV
Create a CSV file (e.g., `my_jobs.csv`) with your jobs:

```csv
job_name,job_file,num_cores
water_opt,/home/user/jobs/water.inp,4
benzene_scf,/home/user/jobs/benzene.inp,8
```

**CSV Columns:**
- `job_name`: Descriptive name for the job (optional, will use filename if not provided)
- `job_file`: Full path to CP2K input file (.inp)
- `num_cores`: Number of CPU cores to use (1-8)

### 4. Run the Job Runner
```bash
python cp2k_job_runner.py my_jobs.csv results.csv
```

The script will:
- Read each job from the CSV
- Run CP2K sequentially
- Parse the output files
- Save results to `results.csv`

## Understanding the Output CSV

The `results.csv` file contains:

| Column | Description |
|--------|-------------|
| `job_name` | Name of the job |
| `job_file` | Path to input file |
| `num_cores` | Cores used |
| `status` | SUCCESS, FAILED, or ERROR |
| `return_code` | System exit code |
| `elapsed_time_sec` | Wall time in seconds |
| `timestamp` | When the job finished |
| `output_file` | Path to .out file |
| `total_energy` | Final energy in Hartree |
| `scf_converged` | True/False |
| `num_scf_steps` | Number of SCF iterations |
| `total_force` | Sum of atomic forces |
| `wall_time` | CP2K reported time |
| `error_message` | Error description if failed |

## Important Notes

### CP2K Executable Issue
⚠️ **Your CP2K build is NOT MPI-enabled!**

Your conda environment shows:
```
cp2k  2024.2  openblas_nompi_hbd0aaf2_1000
```

This means you should:

**Option 1: Use the existing build (OpenMP only)**
```bash
# Set threads before running
export OMP_NUM_THREADS=8

# The script needs modification - change line with mpirun to:
# cmd = ['cp2k.popt', '-i', str(job_file), '-o', str(output_file)]
```

**Option 2: Install MPI-enabled CP2K (RECOMMENDED)**
```bash
conda install -c conda-forge cp2k=*=*mpi*
```

### Manual Script Modification

Since you have the no-MPI version, edit `cp2k_job_runner.py` line 130-137:

**Change from:**
```python
cmd = [
    'mpirun', '-np', str(num_cores),
    'cp2k.psmp',
    '-i', str(job_file),
    '-o', str(output_file)
]
```

**To:**
```python
cmd = [
    'cp2k.popt',  # or just 'cp2k'
    '-i', str(job_file),
    '-o', str(output_file)
]
# And set OMP_NUM_THREADS environment variable
```

## Example Usage

### Create Example Jobs
```bash
python cp2k_job_runner.py --create-example
```

This creates `cp2k_jobs.csv` as a template.

### Run All Jobs
```bash
# Make sure CP2K is in your PATH
which cp2k.popt  # Should show: /home/user/miniconda3/envs/mpi-sim/bin/cp2k.popt

# Set threads
export OMP_NUM_THREADS=8

# Run jobs
python cp2k_job_runner.py my_jobs.csv results.csv
```

### Monitor Progress
The script prints progress to stdout:
```
Starting job: water_opt
Input file: /home/user/jobs/water.inp
Cores: 4
Output file: /home/user/jobs/water_opt.out
============================================================

Job water_opt completed:
  Status: SUCCESS
  Elapsed time: 45.23 seconds
  Total energy: -17.165432 Ha
  SCF converged in 12 steps
```

## Optimal Parameters for Your System

### Intel Xeon w3-2435 (8 cores)

**Small systems (<50 atoms):**
- Cores: 4
- CUTOFF: 400 Ry
- Basis: DZVP-MOLOPT-SR-GTH

**Medium systems (50-200 atoms):**
- Cores: 6
- CUTOFF: 400 Ry  
- Basis: DZVP-MOLOPT-SR-GTH
- Method: OT

**Large systems (>200 atoms):**
- Cores: 8
- CUTOFF: 300-400 Ry (start low)
- Basis: DZVP-MOLOPT-SR-GTH
- Method: OT
- Consider PRECONDITIONER FULL_SINGLE_INVERSE

### Memory Guidelines
- 2-4 GB per core is typical
- Watch with `htop` during first run
- Reduce CUTOFF if memory issues occur

## Troubleshooting

### "cp2k.psmp: command not found"
Your CP2K might be named differently:
```bash
# Check available commands
ls $(conda env list | grep mpi-sim | awk '{print $2}')/bin/cp2k*

# Common names:
# cp2k.popt  - Serial optimized
# cp2k.ssmp  - OpenMP parallel
# cp2k.psmp  - MPI + OpenMP parallel
```

### "SCF did not converge"
Check `results.csv` for the job, then:
1. Look at the output file
2. Increase MAX_SCF
3. Try different MINIMIZER (CG instead of DIIS)
4. Add MIXING section to SCF

### Job runs but no results
Make sure output file paths are accessible and you have write permissions.

### Performance is slow
1. Check OMP_NUM_THREADS is set
2. Verify CPU isn't throttling: `cat /proc/cpuinfo | grep MHz`
3. Reduce CUTOFF for testing
4. Use smaller basis set initially

## Advanced: Batch Processing

Create jobs programmatically:
```python
import pandas as pd
import os

# Generate jobs
jobs = []
for i in range(10):
    jobs.append({
        'job_name': f'structure_{i}',
        'job_file': f'/home/user/structures/struct_{i}.inp',
        'num_cores': 8 if i > 5 else 4  # More cores for later jobs
    })

df = pd.DataFrame(jobs)
df.to_csv('batch_jobs.csv', index=False)
```

Then run: `python cp2k_job_runner.py batch_jobs.csv batch_results.csv`

## Getting Help

1. Check CP2K manual: https://manual.cp2k.org/
2. CP2K forums: https://groups.google.com/g/cp2k
3. Check your output files in the `output_file` path from results CSV
4. Look at error messages in the `error_message` column

## Files Included

- `cp2k_job_runner.py` - Main job runner script
- `cp2k_setup_guide.md` - Detailed CP2K parameter guide
- `example_jobs.csv` - Example job queue
- `example_water_opt.inp` - Example CP2K input file
- `README.md` - This file

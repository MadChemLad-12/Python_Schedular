#!/usr/bin/env python3
"""
Unified CP2K/VASP Job Runner
Runs both CP2K and VASP calculations from a single CSV queue
"""

import pandas as pd
import subprocess
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import re
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO


class VASPParser:
    """Parse VASP output files"""
    
    @staticmethod
    def parse_outcar(outcar_path):
        """
        Extract results from VASP OUTCAR
        
        Returns:
            dict: Results including energy, forces, convergence
        """
        results = {
            'total_energy_eV': None,
            'total_energy_Ha': None,
            'converged': False,
            'ionic_steps': 0,
            'final_forces_max': None,
            'error_message': None
        }
        
        if not os.path.exists(outcar_path):
            results['error_message'] = "OUTCAR not found"
            return results
        
        try:
            with open(outcar_path, 'r') as f:
                content = f.read()
            
            # Extract final energy
            energy_matches = re.findall(r'free  energy   TOTEN\s+=\s+([-\d.]+)\s+eV', content)
            if energy_matches:
                results['total_energy_eV'] = float(energy_matches[-1])
                # Convert to Hartree (1 Ha = 27.2114 eV)
                results['total_energy_Ha'] = results['total_energy_eV'] / 27.2114
            
            # Check convergence
            if 'reached required accuracy' in content:
                results['converged'] = True
            
            # Count ionic steps
            results['ionic_steps'] = len(energy_matches)
            
            # Get final forces
            force_matches = re.findall(r'TOTAL-FORCE.*?\n(.*?)\n.*?-{10}', content, re.DOTALL)
            if force_matches:
                # Parse last force block
                force_lines = force_matches[-1].strip().split('\n')
                max_force = 0.0
                for line in force_lines:
                    parts = line.split()
                    if len(parts) >= 6:
                        fx, fy, fz = float(parts[3]), float(parts[4]), float(parts[5])
                        force = np.sqrt(fx**2 + fy**2 + fz**2)
                        max_force = max(max_force, force)
                results['final_forces_max'] = max_force
            
        except Exception as e:
            results['error_message'] = f"Error parsing OUTCAR: {e}"
        
        return results
    
    @staticmethod
    def parse_oszicar(oszicar_path):
        """
        Extract convergence data from VASP OSZICAR
        
        Returns:
            dict: {
                'energies': list of energies per ionic step,
                'steps': list of step numbers
            }
        """
        energies = []
        steps = []
        
        if not os.path.exists(oszicar_path):
            return None
        
        try:
            with open(oszicar_path, 'r') as f:
                for line in f:
                    # Parse lines like: "  1 F= -.12345678E+03 E0= -.12345678E+03  d E =-.123457E+00"
                    if line.strip() and line.split()[0].isdigit():
                        parts = line.split()
                        step = int(parts[0])
                        # Energy is after F=
                        energy_str = parts[2]
                        energy = float(energy_str)
                        
                        steps.append(step)
                        energies.append(energy)
        
        except Exception as e:
            print(f"Warning: Error parsing OSZICAR: {e}")
            return None
        
        if not energies:
            return None
        
        return {
            'energies': energies,
            'steps': steps
        }


class CP2KParser:
    """Parse CP2K output files"""
    
    @staticmethod
    def parse_output(output_file):
        """Parse CP2K output file"""
        results = {
            'total_energy': None,
            'scf_converged': False,
            'num_scf_steps': None,
            'total_force': None,
            'error_message': None
        }
        
        if not os.path.exists(output_file):
            results['error_message'] = "Output file not found"
            return results
        
        try:
            with open(output_file, 'r') as f:
                content = f.read()
            
            # Extract final energy
            energy_matches = re.findall(r'ENERGY\| Total FORCE_EVAL.*?:\s+([-\d.]+)', content)
            if energy_matches:
                results['total_energy'] = float(energy_matches[-1])
            
            # Check convergence
            if "PROGRAM ENDED AT" in content:
                results['scf_converged'] = True
            
            # Get SCF steps
            scf_matches = re.findall(r'SCF run converged in\s+(\d+)\s+steps', content)
            if scf_matches:
                results['num_scf_steps'] = int(scf_matches[-1])
            
            # Get forces
            force_matches = re.findall(r'SUM OF ATOMIC FORCES\s+([-\d.E+]+)', content)
            if force_matches:
                results['total_force'] = float(force_matches[-1])
        
        except Exception as e:
            results['error_message'] = f"Error parsing output: {e}"
        
        return results
    
    @staticmethod
    def extract_energies_from_output(output_file):
        """Extract all energies from CP2K output for convergence plot"""
        energies = []
        
        if not os.path.exists(output_file):
            return None
        
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    if 'ENERGY| Total FORCE_EVAL' in line:
                        parts = line.split()
                        energy = float(parts[-1])
                        energies.append(energy)
        except Exception as e:
            print(f"Warning: Could not extract energies: {e}")
            return None
        
        if not energies:
            return None
        
        return {
            'energies': energies,
            'steps': list(range(len(energies)))
        }


class Plotter:
    """Generate convergence plots for both CP2K and VASP"""
    
    @staticmethod
    def create_convergence_plot(energies, steps, job_name, code, output_file=None, 
                                energy_unit='eV'):
        """
        Create convergence plot
        
        Args:
            energies: List of energy values
            steps: List of step numbers
            job_name: Job name for title
            code: 'cp2k' or 'vasp'
            output_file: Path to save PNG
            energy_unit: 'eV' or 'Ha'
        
        Returns:
            BytesIO: PNG image buffer
        """
        try:
            plt.figure(figsize=(10, 6), dpi=100)
            
            steps = np.array(steps)
            energies = np.array(energies)
            
            # Plot
            plt.plot(steps, energies, 'o-', linewidth=2, markersize=4, label='Energy')
            plt.xlabel('Step', fontsize=12, fontweight='bold')
            plt.ylabel(f'Energy ({energy_unit})', fontsize=12, fontweight='bold')
            
            title = f'Convergence - {job_name}'
            if code == 'vasp':
                title += ' (VASP)'
            elif code == 'cp2k':
                title += ' (CP2K)'
            plt.title(title, fontsize=14, fontweight='bold')
            
            plt.grid(True, alpha=0.3)
            plt.legend()
            
            # Statistics
            if len(energies) > 1:
                initial = energies[0]
                final = energies[-1]
                minimum = np.min(energies)
                change = final - initial
                
                stats_text = f'Initial: {initial:.6f} {energy_unit}\n'
                stats_text += f'Final: {final:.6f} {energy_unit}\n'
                stats_text += f'Minimum: {minimum:.6f} {energy_unit}\n'
                stats_text += f'Change: {change:.6f} {energy_unit}'
                
                plt.text(0.02, 0.98, stats_text,
                        transform=plt.gca().transAxes,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                        fontsize=10, fontfamily='monospace')
            
            plt.tight_layout()
            
            # Save to file
            if output_file:
                plt.savefig(output_file, dpi=100, bbox_inches='tight')
                print(f"  📊 Convergence plot saved: {output_file}")
            
            # Save to buffer
            img_buffer = BytesIO()
            plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
            img_buffer.seek(0)
            
            plt.close()
            
            return img_buffer
        
        except Exception as e:
            print(f"Error creating convergence plot: {e}")
            if 'plt' in dir():
                plt.close()
            return None


class Notifier:
    """Handle Slack/Email/Teams notifications"""
    
    def __init__(self, config_file=None):
        self.slack_enabled = False
        self.email_enabled = False
        self.teams_enabled = False
        self.config = {}
        
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
    
    def load_config(self, config_file):
        """Load notification config from JSON"""
        try:
            with open(config_file, 'r') as f:
                self.config = json.load(f)
            
            # Slack
            slack_config = self.config.get('slack', {})
            if slack_config.get('enabled', False):
                self.slack_enabled = True
                self.slack_webhook = slack_config.get('webhook_url')
                print(f"✓ Slack notifications enabled")
            
            # Email
            email_config = self.config.get('email', {})
            if email_config.get('enabled', False):
                self.email_enabled = True
                self.smtp_server = email_config.get('smtp_server')
                self.smtp_port = email_config.get('smtp_port', 587)
                self.sender_email = email_config.get('sender_email')
                self.sender_password = email_config.get('sender_password')
                self.recipient_email = email_config.get('recipient_email')
                print(f"✓ Email notifications enabled")
            
            # Teams
            teams_config = self.config.get('teams', {})
            if teams_config.get('enabled', False):
                self.teams_enabled = True
                self.teams_webhook = teams_config.get('webhook_url')
                print(f"✓ Teams notifications enabled")
        
        except Exception as e:
            print(f"Warning: Could not load notification config: {e}")
    
    def send_slack(self, result, time_remaining=None):
        """Send Slack notification"""
        if not self.slack_enabled:
            return False
        
        try:
            status = result['status']
            job_name = result['job_name']
            code = result.get('code', 'unknown').upper()
            
            # Emoji and color
            if status == 'SUCCESS':
                emoji = '✅'
                color = 'good'
            elif status == 'TIMEOUT':
                emoji = '⏰'
                color = 'warning'
            else:
                emoji = '❌'
                color = 'danger'
            
            # Build message
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {code} Job {status}: {job_name}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Code:*\n{code}"},
                        {"type": "mrkdwn", "text": f"*Status:*\n{status}"},
                        {"type": "mrkdwn", "text": f"*Elapsed:*\n{result.get('elapsed_time_hours', 0):.4f} hours"},
                    ]
                }
            ]
            
            # Time remaining
            if time_remaining and time_remaining > 0:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏱️ *Estimated time remaining:* {time_remaining:.1f} hours ({time_remaining/24:.1f} days)"
                    }
                })
            
            # Energy info
            if result.get('total_energy_eV'):
                fields = [
                    {"type": "mrkdwn", "text": f"*Energy (eV):*\n{result['total_energy_eV']:.6f}"},
                    {"type": "mrkdwn", "text": f"*Energy (Ha):*\n{result['total_energy_Ha']:.8f}"},
                ]
                
                if result.get('converged') is not None:
                    fields.append({
                        "type": "mrkdwn",
                        "text": f"*Converged:*\n{'Yes ✓' if result['converged'] else 'No ✗'}"
                    })
                
                if result.get('ionic_steps'):
                    fields.append({
                        "type": "mrkdwn",
                        "text": f"*Ionic Steps:*\n{result['ionic_steps']}"
                    })
                
                blocks.append({"type": "section", "fields": fields})
            
            # Error message
            if result.get('error_message'):
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *Error:*\n```{result['error_message']}```"
                    }
                })
            
            # Timestamp
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"Completed at {result.get('timestamp', 'N/A')}"
                }]
            })
            
            payload = {
                "blocks": blocks,
                "attachments": [{"color": color}]
            }
            
            response = requests.post(self.slack_webhook, json=payload, timeout=10)
            return response.status_code == 200
        
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False
    
    def notify_job_complete(self, result, time_remaining=None):
        """Send notifications when job completes"""
        if self.slack_enabled:
            self.send_slack(result, time_remaining)
            print(f"  💬 Slack notification sent")
    
    def notify_queue_complete(self, summary):
        """Notify when entire queue completes"""
        if not self.slack_enabled:
            return
        
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🏁 Queue Complete: {summary['total']} Jobs Finished",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Total:*\n{summary['total']}"},
                        {"type": "mrkdwn", "text": f"*✅ Success:*\n{summary['success']}"},
                        {"type": "mrkdwn", "text": f"*❌ Failed:*\n{summary['failed']}"},
                        {"type": "mrkdwn", "text": f"*⏰ Timeout:*\n{summary['timeout']}"},
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Total Time:*\n{summary['total_time_hours']:.2f} hours"},
                        {"type": "mrkdwn", "text": f"*Average:*\n{summary['avg_time_hours']:.4f} hours/job"},
                    ]
                }
            ]
            
            payload = {"blocks": blocks, "attachments": [{"color": "good"}]}
            requests.post(self.slack_webhook, json=payload, timeout=10)
        
        except Exception as e:
            print(f"Failed to send queue complete notification: {e}")


class UnifiedJobRunner:
    """Run both CP2K and VASP jobs from a single CSV queue"""
    
    def __init__(self, input_csv, output_csv="results.csv", wall_time_hours=24, 
                 notify_config=None):
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.wall_time_hours = wall_time_hours
        self.results = []
        
        self.notifier = Notifier(notify_config)
        
        self.cp2k_parser = CP2KParser()
        self.vasp_parser = VASPParser()
        self.plotter = Plotter()
    
    def read_jobs(self):
        """Read job queue from CSV"""
        try:
            df = pd.read_csv(self.input_csv)
            
            required_cols = ['job_name', 'code', 'job_path', 'num_cores']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")
            
            if 'wall_time_hours' not in df.columns:
                df['wall_time_hours'] = self.wall_time_hours
            
            if 'executable' not in df.columns:
                # Default executables
                df['executable'] = df['code'].apply(
                    lambda x: 'ssmp' if x == 'cp2k' else 'vasp_std'
                )
            
            # Validate codes
            valid_codes = {'cp2k', 'vasp'}
            invalid = df[~df['code'].isin(valid_codes)]
            if not invalid.empty:
                raise ValueError(f"Invalid code(s): {invalid['code'].unique()}")
            
            return df
        
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    
    def get_time_remaining(self, completed_jobs):
        """Calculate estimated time remaining"""
        try:
            df = pd.read_csv(self.input_csv)
            if 'wall_time_hours' not in df.columns:
                df['wall_time_hours'] = self.wall_time_hours
            
            if completed_jobs < len(df):
                remaining = df.iloc[completed_jobs:]
                return float(remaining['wall_time_hours'].sum())
            return 0.0
        except:
            return 0.0
    
    def run_cp2k_job(self, job_path, num_cores, job_name, wall_time_hours, executable):
        """Run a CP2K job"""
        job_path = Path(job_path)
        job_dir = job_path.parent
        output_file = job_dir / f"{job_name}.out"
        
        # Build command
        cmd = [
            f'cp2k.{executable}',
            '-i', str(job_path),
            '-o', str(output_file)
        ]
        
        # Environment
        env = os.environ.copy()
        env['OMP_NUM_THREADS'] = str(num_cores)
        env['OMP_PROC_BIND'] = 'close'
        env['OMP_PLACES'] = 'cores'
        
        print(f"  🐍 Running CP2K ({executable})")
        print(f"  🧵 OpenMP threads: {num_cores}")
        
        # Run
        start_time = time.time()
        wall_time_sec = int(wall_time_hours * 3600)
        
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=wall_time_sec,
                cwd=str(job_dir)
            )
            
            elapsed = time.time() - start_time
            
            # Parse output
            parsed = self.cp2k_parser.parse_output(output_file)
            
            # Get convergence data
            conv_data = self.cp2k_parser.extract_energies_from_output(output_file)
            
            # Create convergence plot
            plot_file = None
            if conv_data:
                plot_file = job_dir / f"{job_name}_convergence.png"
                self.plotter.create_convergence_plot(
                    conv_data['energies'],
                    conv_data['steps'],
                    job_name,
                    'cp2k',
                    str(plot_file),
                    energy_unit='Ha'
                )
            
            return {
                'job_name': job_name,
                'code': 'cp2k',
                'job_path': str(job_path),
                'num_cores': num_cores,
                'executable': executable,
                'status': 'SUCCESS' if result.returncode == 0 else 'FAILED',
                'elapsed_time_hours': elapsed / 3600,
                'total_energy_Ha': parsed['total_energy'],
                'total_energy_eV': parsed['total_energy'] * 27.2114 if parsed['total_energy'] else None,
                'converged': parsed['scf_converged'],
                'error_message': parsed['error_message'],
                'convergence_plot': str(plot_file) if plot_file else None,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return {
                'job_name': job_name,
                'code': 'cp2k',
                'status': 'TIMEOUT',
                'elapsed_time_hours': elapsed / 3600,
                'error_message': f'Exceeded {wall_time_hours} hour limit',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                'job_name': job_name,
                'code': 'cp2k',
                'status': 'ERROR',
                'elapsed_time_hours': elapsed / 3600,
                'error_message': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def run_vasp_job(self, job_path, num_cores, job_name, wall_time_hours, executable):
        """Run a VASP job using Popen (like your working vasprun.py)"""
        job_dir = Path(job_path)
        
        # Verify directory exists
        if not job_dir.exists():
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'error_message': f"Directory not found: {job_dir}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # Check required files
        required = ['INCAR', 'POSCAR', 'POTCAR', 'KPOINTS']
        missing = [f for f in required if not (job_dir / f).exists()]
        if missing:
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'error_message': f"Missing required files in {job_dir}: {missing}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # Determine VASP binary path
        if '/' in executable:
            # Full path provided
            vasp_binary = executable
        else:
            # Try common locations
            vasp_bin = os.environ.get('VASP_BIN', '/home/user/Documents/Models/vasp.6.5.1/bin')
            vasp_binary = os.path.join(vasp_bin, executable)
        
        if not os.path.exists(vasp_binary):
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'error_message': f"VASP binary not found: {vasp_binary}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # MPI launcher
        mpirun = '/usr/lib64/openmpi/bin/mpirun'
        if not os.path.exists(mpirun):
            # Try to find in PATH
            try:
                result = subprocess.run(['which', 'mpirun'], capture_output=True, text=True)
                if result.returncode == 0:
                    mpirun = result.stdout.strip()
                else:
                    mpirun = 'mpirun'  # Hope it's in PATH
            except:
                mpirun = 'mpirun'
        
        # Build command (like your vasprun.py)
        cmd = [mpirun,
        '-np', str(num_cores),
        '--bind-to', 'core',
        '--map-by', 'core',
        
        vasp_binary
        ]
        
        # Environment (keep current environment, works with conda active)
        env = os.environ.copy()
        # VASP can use threads too (hybrid MPI+OpenMP)
        env['OMP_NUM_THREADS'] = '1'  # Use 1 thread per MPI rank for VASP
        
        print(f"  🔬 Running VASP ({os.path.basename(vasp_binary)})")
        print(f"  🌐 MPI processes: {num_cores}")
        print(f"  📂 Working directory: {job_dir}")
        print(f"  🔧 Command: {' '.join(cmd)}")
        
        # Run using Popen (like your working script)
        start_time = time.time()
        wall_time_sec = int(wall_time_hours * 3600)
        
        try:
            # Start process
            process = subprocess.Popen(
                cmd,
                cwd=str(job_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor with timeout (like your vasprun.py)
            poll_interval = 10  # Check every 10 seconds
            while True:
                time.sleep(poll_interval)
                
                # Check if process finished
                if process.poll() is not None:
                    print(f"  ✓ VASP process finished")
                    break
                
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > wall_time_sec:
                    print(f"  ⏰ Exceeded wall time limit, terminating...")
                    process.terminate()
                    time.sleep(5)
                    if process.poll() is None:
                        process.kill()
                    
                    return {
                        'job_name': job_name,
                        'code': 'vasp',
                        'status': 'TIMEOUT',
                        'elapsed_time_hours': elapsed / 3600,
                        'error_message': f'Exceeded {wall_time_hours} hour limit',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
            
            # Get final elapsed time
            elapsed = time.time() - start_time
            
            # Check return code
            return_code = process.returncode
            
            # Parse OUTCAR
            outcar = job_dir / 'OUTCAR'
            parsed = self.vasp_parser.parse_outcar(outcar)
            
            # Get convergence data from OSZICAR
            oszicar = job_dir / 'OSZICAR'
            conv_data = self.vasp_parser.parse_oszicar(oszicar)
            
            # Create convergence plot
            plot_file = None
            if conv_data:
                plot_file = job_dir / f"{job_name}_convergence.png"
                self.plotter.create_convergence_plot(
                    conv_data['energies'],
                    conv_data['steps'],
                    job_name,
                    'vasp',
                    str(plot_file),
                    energy_unit='eV'
                )
            
            # Determine status
            if return_code == 0 and parsed.get('converged'):
                status = 'SUCCESS'
            elif return_code == 0:
                status = 'COMPLETED'  # Finished but maybe not converged
            else:
                status = 'FAILED'
            
            return {
                'job_name': job_name,
                'code': 'vasp',
                'job_path': str(job_dir),
                'num_cores': num_cores,
                'executable': os.path.basename(vasp_binary),
                'status': status,
                'return_code': return_code,
                'elapsed_time_hours': elapsed / 3600,
                'total_energy_eV': parsed['total_energy_eV'],
                'total_energy_Ha': parsed['total_energy_Ha'],
                'converged': parsed['converged'],
                'ionic_steps': parsed['ionic_steps'],
                'error_message': parsed['error_message'],
                'convergence_plot': str(plot_file) if plot_file else None,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'elapsed_time_hours': elapsed / 3600,
                'error_message': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        """Run a VASP job"""
        job_dir = Path(job_path)
        
        # Verify directory exists
        if not job_dir.exists():
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'error_message': f"Directory not found: {job_dir}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # Check required files
        required = ['INCAR', 'POSCAR', 'POTCAR', 'KPOINTS']
        missing = [f for f in required if not (job_dir / f).exists()]
        if missing:
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'error_message': f"Missing required files in {job_dir}: {missing}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # Check if executable is a full path or needs to be found
        if '/' in executable:
            # Full path provided
            vasp_binary = executable
            if not os.path.exists(vasp_binary):
                return {
                    'job_name': job_name,
                    'code': 'vasp',
                    'status': 'ERROR',
                    'error_message': f"VASP binary not found: {vasp_binary}",
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        else:
            # Try to find in PATH or common locations
            vasp_binary = executable
            
            # Check common VASP locations if not in PATH
            try:
                result = subprocess.run(['which', vasp_binary], capture_output=True, text=True)
                if result.returncode != 0:
                    # Not in PATH, check VASP_BIN environment variable
                    vasp_bin = os.environ.get('VASP_BIN')
                    if vasp_bin:
                        test_path = os.path.join(vasp_bin, executable)
                        if os.path.exists(test_path):
                            vasp_binary = test_path
                            print(f"  ℹ️  Found VASP at: {vasp_binary}")
                        else:
                            return {
                                'job_name': job_name,
                                'code': 'vasp',
                                'status': 'ERROR',
                                'error_message': f"VASP executable '{executable}' not found. Try using full path in CSV.",
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                    else:
                        return {
                            'job_name': job_name,
                            'code': 'vasp',
                            'status': 'ERROR',
                            'error_message': f"VASP executable '{executable}' not in PATH. Set VASP_BIN or use full path in CSV.",
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
            except Exception as e:
                return {
                    'job_name': job_name,
                    'code': 'vasp',
                    'status': 'ERROR',
                    'error_message': f"Could not locate VASP: {e}",
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        
        # Build command
        cmd = ['mpirun', '-np', str(num_cores), vasp_binary]
        
        # Environment (keep conda as-is since your VASP works with it)
        env = os.environ.copy()
        
        print(f"  🔬 Running VASP ({executable})")
        print(f"  🌐 MPI processes: {num_cores}")
        print(f"  📂 Working directory: {job_dir}")
        
        # Run
        start_time = time.time()
        wall_time_sec = int(wall_time_hours * 3600)
        
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=wall_time_sec,
                cwd=str(job_dir)
            )
            
            elapsed = time.time() - start_time
            
            # Parse OUTCAR
            outcar = job_dir / 'OUTCAR'
            parsed = self.vasp_parser.parse_outcar(outcar)
            
            # Get convergence data from OSZICAR
            oszicar = job_dir / 'OSZICAR'
            conv_data = self.vasp_parser.parse_oszicar(oszicar)
            
            # Create convergence plot
            plot_file = None
            if conv_data:
                plot_file = job_dir / f"{job_name}_convergence.png"
                self.plotter.create_convergence_plot(
                    conv_data['energies'],
                    conv_data['steps'],
                    job_name,
                    'vasp',
                    str(plot_file),
                    energy_unit='eV'
                )
            
            return {
                'job_name': job_name,
                'code': 'vasp',
                'job_path': str(job_dir),
                'num_cores': num_cores,
                'executable': executable,
                'status': 'SUCCESS' if result.returncode == 0 else 'FAILED',
                'elapsed_time_hours': elapsed / 3600,
                'total_energy_eV': parsed['total_energy_eV'],
                'total_energy_Ha': parsed['total_energy_Ha'],
                'converged': parsed['converged'],
                'ionic_steps': parsed['ionic_steps'],
                'error_message': parsed['error_message'],
                'convergence_plot': str(plot_file) if plot_file else None,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'TIMEOUT',
                'elapsed_time_hours': elapsed / 3600,
                'error_message': f'Exceeded {wall_time_hours} hour limit',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                'job_name': job_name,
                'code': 'vasp',
                'status': 'ERROR',
                'elapsed_time_hours': elapsed / 3600,
                'error_message': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def run_all_jobs(self):
        """Run all jobs in the queue"""
        jobs_df = self.read_jobs()
        total_jobs = len(jobs_df)
        
        print(f"\n{'='*60}")
        print(f"Unified CP2K/VASP Job Runner")
        print(f"{'='*60}")
        print(f"Total jobs: {total_jobs}")
        
        # Count by code
        cp2k_count = len(jobs_df[jobs_df['code'] == 'cp2k'])
        vasp_count = len(jobs_df[jobs_df['code'] == 'vasp'])
        print(f"  CP2K jobs: {cp2k_count}")
        print(f"  VASP jobs: {vasp_count}")
        print(f"{'='*60}\n")
        
        for idx, row in jobs_df.iterrows():
            job_name = row['job_name']
            code = row['code']
            job_path = row['job_path']
            num_cores = int(row['num_cores'])
            wall_time_hours = row['wall_time_hours']
            executable = row['executable']
            
            print(f"\n{'='*60}")
            print(f"Starting job: {job_name} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Progress: [{idx+1}/{total_jobs}]")
            print(f"Code: {code.upper()}")
            print(f"Path: {job_path}")
            print(f"Cores: {num_cores}")
            print(f"Wall time: {wall_time_hours} hours")
            
            # Calculate time remaining
            time_remaining = self.get_time_remaining(idx + 1)
            if time_remaining > 0:
                print(f"⏱️  Estimated time remaining: {time_remaining:.1f} hours ({time_remaining/24:.1f} days)")
            
            print(f"{'='*60}\n")
            
            # Run appropriate code
            try:
                if code == 'cp2k':
                    result = self.run_cp2k_job(
                        job_path, num_cores, job_name, wall_time_hours, executable
                    )
                elif code == 'vasp':
                    result = self.run_vasp_job(
                        job_path, num_cores, job_name, wall_time_hours, executable
                    )
                else:
                    result = {
                        'job_name': job_name,
                        'code': code,
                        'status': 'ERROR',
                        'error_message': f'Unknown code: {code}',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                
                self.results.append(result)
                self.save_results()
                
                # Print result
                print(f"\n✓ Job {job_name} completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:")
                print(f"  Status: {result['status']}")
                print(f"  Time: {result.get('elapsed_time_hours', 0):.4f} hours")
                if result.get('total_energy_eV'):
                    print(f"  Energy: {result['total_energy_eV']:.6f} eV")
                if result.get('convergence_plot'):
                    print(f"  📊 Convergence plot: {result['convergence_plot']}")
                
                # Notify
                self.notifier.notify_job_complete(result, time_remaining)
            
            except Exception as e:
                print(f"\n⚠️ Error running job {job_name}: {e}")
                error_result = {
                    'job_name': job_name,
                    'code': code,
                    'status': 'ERROR',
                    'error_message': str(e),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                self.results.append(error_result)
                self.save_results()
        
        # Queue complete
        print(f"\n{'='*60}")
        print(f"All jobs completed!")
        print(f"{'='*60}\n")
        
        summary = self.print_summary()
        self.notifier.notify_queue_complete(summary)
    
    def save_results(self):
        """Save results to CSV"""
        df = pd.DataFrame(self.results)
        df.to_csv(self.output_csv, index=False)
    
    def print_summary(self):
        """Print summary statistics"""
        df = pd.DataFrame(self.results)
        
        summary = {
            'total': len(df),
            'success': len(df[df['status'] == 'SUCCESS']),
            'failed': len(df[df['status'] == 'FAILED']),
            'timeout': len(df[df['status'] == 'TIMEOUT']),
            'total_time_hours': 0,
            'avg_time_hours': 0
        }
        
        print("\nJob Summary:")
        print(f"  Total: {summary['total']}")
        print(f"  ✅ Success: {summary['success']}")
        print(f"  ❌ Failed: {summary['failed']}")
        print(f"  ⏰ Timeout: {summary['timeout']}")
        
        if 'elapsed_time_hours' in df.columns:
            summary['total_time_hours'] = df['elapsed_time_hours'].sum()
            summary['avg_time_hours'] = df['elapsed_time_hours'].mean()
            print(f"  ⏱️  Total: {summary['total_time_hours']:.2f} hours")
            print(f"  ⏱️  Avg: {summary['avg_time_hours']:.4f} hours/job")
        
        # By code
        for code in ['cp2k', 'vasp']:
            code_df = df[df['code'] == code]
            if not code_df.empty:
                print(f"\n  {code.upper()} jobs: {len(code_df)}")
                print(f"    Success: {len(code_df[code_df['status'] == 'SUCCESS'])}")
        
        return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Unified CP2K/VASP Job Runner")
        print("="*60)
        print("\nUsage: python unified_runner.py <input_csv> [options]")
        print("\nRequired CSV columns:")
        print("  job_name      - Name for the job")
        print("  code          - 'cp2k' or 'vasp'")
        print("  job_path      - CP2K: path to .inp file, VASP: directory path")
        print("  num_cores     - Number of cores")
        print("\nOptional CSV columns:")
        print("  wall_time_hours - Wall time limit (default: 24)")
        print("  executable      - cp2k: ssmp/psmp, vasp: vasp_std/vasp_gam/vasp_ncl")
        print("\nOptions:")
        print("  --output <file>         : Output CSV (default: results.csv)")
        print("  --walltime <hours>      : Default wall time (default: 24)")
        print("  --notify-config <file>  : Notification config JSON")
        print("\nExample CSV:")
        print("  job_name,code,job_path,num_cores,wall_time_hours,executable")
        print("  water_opt,cp2k,/data/water.inp,8,12,ssmp")
        print("  Pt2_charge,vasp,/data/vasp/Pt2+,8,24,vasp_gam")
        sys.exit(1)
    
    # Parse arguments
    input_csv = sys.argv[1]
    output_csv = "results.csv"
    wall_time_hours = 24
    notify_config = None
    
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--output' and i+1 < len(sys.argv):
            output_csv = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == '--walltime' and i+1 < len(sys.argv):
            wall_time_hours = float(sys.argv[i+1])
            i += 2
        elif sys.argv[i] == '--notify-config' and i+1 < len(sys.argv):
            notify_config = sys.argv[i+1]
            i += 2
        else:
            i += 1
    
    if not os.path.exists(input_csv):
        print(f"ERROR: Input CSV not found: {input_csv}")
        sys.exit(1)
    
    print("\nInitializing Unified Job Runner...")
    runner = UnifiedJobRunner(input_csv, output_csv, wall_time_hours, notify_config)
    runner.run_all_jobs()
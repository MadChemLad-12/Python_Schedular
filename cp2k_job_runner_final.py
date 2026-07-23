#!/usr/bin/env python3
"""
CP2K Job Runner - Final Version with Plotting and CIF Export
Beautiful HTML emails with energy plots and structure export
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
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64


class StructureHandler:
    """Handle structure parsing and CIF export"""
    
    @staticmethod
    def get_project_name(input_file):
        """
        Extract PROJECT_NAME from CP2K input file
        
        Returns:
            str: Project name or None if not found
        """
        if not os.path.exists(input_file):
            return None
        
        try:
            with open(input_file, 'r') as f:
                content = f.read()
            
            # Look for PROJECT or PROJECT_NAME
            # Format: PROJECT bot_wet0.75 or PROJECT_NAME bot_wet0.75
            project_match = re.search(
                r'PROJECT(?:_NAME)?\s+(\S+)',
                content,
                re.IGNORECASE
            )
            
            if project_match:
                project_name = project_match.group(1).strip()
                print(f"  ✓ Found PROJECT_NAME: {project_name}")
                return project_name
            
        except Exception as e:
            print(f"  Warning: Could not extract PROJECT_NAME: {e}")
        
        return None
    
    @staticmethod
    def parse_xyz_trajectory(xyz_file):
        """
        Parse CP2K pos-1.xyz trajectory file
        
        Returns:
            dict: {
                'energies': list of energies,
                'steps': list of step numbers,
                'structures': list of structures (atom positions),
                'cell': cell parameters if available
            }
        """
        if not os.path.exists(xyz_file):
            return None
        
        energies = []
        steps = []
        structures = []
        cell = None
        
        try:
            with open(xyz_file, 'r') as f:
                lines = f.readlines()
            
            i = 0
            while i < len(lines):
                # Read number of atoms
                try:
                    n_atoms = int(lines[i].strip())
                except (ValueError, IndexError):
                    break
                
                # Read comment line (contains energy and step info)
                if i + 1 < len(lines):
                    comment = lines[i + 1].strip()
                    
                    # Extract energy (various CP2K formats)
                    # Format 1: "i = 10, E = -123.456"
                    # Format 2: "i = 10, time = 1.0, E = -123.456"
                    # Format 3: just the energy value
                    energy_match = re.search(r'E\s*=\s*([-\d.]+)', comment)
                    if energy_match:
                        energy = float(energy_match.group(1))
                        energies.append(energy)
                    
                    # Extract step number
                    step_match = re.search(r'i\s*=\s*(\d+)', comment)
                    if step_match:
                        step = int(step_match.group(1))
                        steps.append(step)
                    elif len(steps) > 0:
                        steps.append(steps[-1] + 1)
                    else:
                        steps.append(len(steps))
                
                # Read atomic positions
                structure = []
                for j in range(n_atoms):
                    if i + 2 + j < len(lines):
                        atom_line = lines[i + 2 + j].strip().split()
                        if len(atom_line) >= 4:
                            structure.append({
                                'element': atom_line[0],
                                'x': float(atom_line[1]),
                                'y': float(atom_line[2]),
                                'z': float(atom_line[3])
                            })
                
                if structure:
                    structures.append(structure)
                
                i += n_atoms + 2
        
        except Exception as e:
            print(f"Warning: Error parsing XYZ file: {e}")
            return None
        
        if not energies:
            return None
        
        return {
            'energies': energies,
            'steps': steps if steps else list(range(len(energies))),
            'structures': structures,
            'cell': cell
        }
    
    @staticmethod
    def parse_cell_from_input(input_file):
        """
        Extract cell parameters from CP2K input file
        
        Returns:
            dict: {'a': float, 'b': float, 'c': float, 
                   'alpha': float, 'beta': float, 'gamma': float}
        """
        if not os.path.exists(input_file):
            return None
        
        try:
            with open(input_file, 'r') as f:
                content = f.read()
            
            # Look for CELL section
            # Format: A B C or ABC + ALPHA BETA GAMMA
            cell_match = re.search(
                r'&CELL.*?A\s+([\d.]+).*?B\s+([\d.]+).*?C\s+([\d.]+)',
                content, re.DOTALL | re.IGNORECASE
            )
            
            if cell_match:
                a = float(cell_match.group(1))
                b = float(cell_match.group(2))
                c = float(cell_match.group(3))
                
                # Look for angles (default to 90 if not found)
                alpha_match = re.search(r'ALPHA\s+([\d.]+)', content, re.IGNORECASE)
                beta_match = re.search(r'BETA\s+([\d.]+)', content, re.IGNORECASE)
                gamma_match = re.search(r'GAMMA\s+([\d.]+)', content, re.IGNORECASE)
                
                alpha = float(alpha_match.group(1)) if alpha_match else 90.0
                beta = float(beta_match.group(1)) if beta_match else 90.0
                gamma = float(gamma_match.group(1)) if gamma_match else 90.0
                
                return {
                    'a': a, 'b': b, 'c': c,
                    'alpha': alpha, 'beta': beta, 'gamma': gamma
                }
            
            # Alternative format: ABC in one line
            abc_match = re.search(
                r'ABC\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
                content, re.IGNORECASE
            )
            if abc_match:
                return {
                    'a': float(abc_match.group(1)),
                    'b': float(abc_match.group(2)),
                    'c': float(abc_match.group(3)),
                    'alpha': 90.0, 'beta': 90.0, 'gamma': 90.0
                }
        
        except Exception as e:
            print(f"Warning: Could not parse cell from input file: {e}")
        
        return None
    
    @staticmethod
    def write_cif(structure, cell, output_file):
        """
        Write structure to CIF format
        
        Args:
            structure: List of atoms with {element, x, y, z}
            cell: Dict with cell parameters
            output_file: Path to output CIF file
        """
        try:
            with open(output_file, 'w') as f:
                f.write("data_optimised_structure\n\n")
                
                # Cell parameters
                f.write(f"_cell_length_a    {cell['a']:.6f}\n")
                f.write(f"_cell_length_b    {cell['b']:.6f}\n")
                f.write(f"_cell_length_c    {cell['c']:.6f}\n")
                f.write(f"_cell_angle_alpha {cell['alpha']:.6f}\n")
                f.write(f"_cell_angle_beta  {cell['beta']:.6f}\n")
                f.write(f"_cell_angle_gamma {cell['gamma']:.6f}\n")
                f.write("_symmetry_space_group_name_H-M    'P 1'\n")
                f.write("_symmetry_Int_Tables_number       1\n\n")
                
                # Atom site loop
                f.write("loop_\n")
                f.write("_atom_site_label\n")
                f.write("_atom_site_type_symbol\n")
                f.write("_atom_site_fract_x\n")
                f.write("_atom_site_fract_y\n")
                f.write("_atom_site_fract_z\n")
                
                # Convert Cartesian to fractional coordinates
                for i, atom in enumerate(structure):
                    # Simple conversion (assumes orthogonal cell)
                    # For non-orthogonal cells, would need proper transformation
                    frac_x = atom['x'] / cell['a']
                    frac_y = atom['y'] / cell['b']
                    frac_z = atom['z'] / cell['c']
                    
                    label = f"{atom['element']}{i+1}"
                    f.write(f"{label:8s} {atom['element']:4s} "
                           f"{frac_x:12.8f} {frac_y:12.8f} {frac_z:12.8f}\n")
            
            return True
        except Exception as e:
            print(f"Error writing CIF file: {e}")
            return False


class EnergyPlotter:
    """Handle energy plot generation"""
    
    @staticmethod
    def create_energy_plot(energies, steps, job_name, output_file=None):
        """
        Create energy vs step plot
        
        Args:
            energies: List of energy values
            steps: List of step numbers
            job_name: Name of the job for title
            output_file: Path to save plot (optional)
            
        Returns:
            BytesIO: Plot as PNG in memory
        """
        try:
            plt.figure(figsize=(10, 6), dpi=100)
            
            # Convert to numpy arrays
            steps = np.array(steps)
            energies = np.array(energies)
            
            # Plot energy
            plt.plot(steps, energies, 'b-', linewidth=2, label='Energy')
            plt.xlabel('Step', fontsize=12, fontweight='bold')
            plt.ylabel('Energy (Hartree)', fontsize=12, fontweight='bold')
            plt.title(f'Energy Evolution - {job_name}', fontsize=14, fontweight='bold')
            plt.grid(True, alpha=0.3)
            plt.legend()
            
            #Export data as csv
            #df_excel = pd.DataFrame({"Steps": steps, "Energy": energies})
            #df_excel.to_csv(f"{job_name}_energy_data.csv", index=False)
            # Add statistics box
            final_energy = energies[-1]
            min_energy = np.min(energies)
            energy_change = energies[-1] - energies[0]
            
            stats_text = f'Final: {final_energy:.6f} Ha\n'
            stats_text += f'Minimum: {min_energy:.6f} Ha\n'
            stats_text += f'Change: {energy_change:.6f} Ha'
            
            plt.text(0.02, 0.98, stats_text,
                    transform=plt.gca().transAxes,
                    verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                    fontsize=10, fontfamily='monospace')
            
            plt.tight_layout()
            
            # Save to file if requested
            if output_file:
                plt.savefig(output_file, dpi=100, bbox_inches='tight')
                print(f"  📊 Energy plot saved: {output_file}")
            
            # Save to BytesIO for email
            img_buffer = BytesIO()
            plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
            img_buffer.seek(0)
            
            plt.close()
            
            return img_buffer
            
        except Exception as e:
            print(f"Error creating energy plot: {e}")
            plt.close()
            return None


class Notifier:
    """Handle various notification methods with HTML email support"""
    
    def __init__(self, config_file=None, notify_mode='complete'):
        self.email_enabled = False
        self.teams_enabled = False
        self.linework_enabled = False
        self.slack_enabled = False  # Added Slack
        self.config = {}
        self.notify_mode = notify_mode
        
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
        else:
            self.load_from_env()
    
    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                self.config = json.load(f)
            
            email_config = self.config.get('email', {})
            if email_config.get('enabled', False):
                self.email_enabled = True
                self.smtp_server = email_config.get('smtp_server')
                self.smtp_port = email_config.get('smtp_port', 587)
                self.sender_email = email_config.get('sender_email')
                self.sender_password = email_config.get('sender_password')
                self.recipient_email = email_config.get('recipient_email')
                print(f"✓ Email notifications enabled: {self.recipient_email}")
            
            teams_config = self.config.get('teams', {})
            if teams_config.get('enabled', False):
                self.teams_enabled = True
                self.teams_webhook = teams_config.get('webhook_url')
                print(f"✓ Microsoft Teams notifications enabled")
            
            linework_config = self.config.get('linework', {})
            if linework_config.get('enabled', False):
                self.linework_enabled = True
                self.linework_webhook = linework_config.get('webhook_url')
                print(f"✓ LINE Work notifications enabled")
            
            # Slack configuration
            slack_config = self.config.get('slack', {})
            if slack_config.get('enabled', False):
                self.slack_enabled = True
                self.slack_webhook = slack_config.get('webhook_url')
                print(f"✓ Slack notifications enabled")
                
        except Exception as e:
            print(f"Warning: Could not load notification config: {e}")
    
    def load_from_env(self):
        """Load configuration from environment variables"""
        if os.environ.get('NOTIFY_EMAIL_ENABLED', '').lower() == 'true':
            self.email_enabled = True
            self.smtp_server = os.environ.get('NOTIFY_SMTP_SERVER')
            self.smtp_port = int(os.environ.get('NOTIFY_SMTP_PORT', 587))
            self.sender_email = os.environ.get('NOTIFY_SENDER_EMAIL')
            self.sender_password = os.environ.get('NOTIFY_SENDER_PASSWORD')
            self.recipient_email = os.environ.get('NOTIFY_RECIPIENT_EMAIL')
            print(f"✓ Email notifications enabled from env: {self.recipient_email}")
        
        if os.environ.get('NOTIFY_TEAMS_ENABLED', '').lower() == 'true':
            self.teams_enabled = True
            self.teams_webhook = os.environ.get('NOTIFY_TEAMS_WEBHOOK')
            print(f"✓ Microsoft Teams notifications enabled from env")
        
        if os.environ.get('NOTIFY_LINEWORK_ENABLED', '').lower() == 'true':
            self.linework_enabled = True
            self.linework_webhook = os.environ.get('NOTIFY_LINEWORK_WEBHOOK')
            print(f"✓ LINE Work notifications enabled from env")
        
        # Slack from environment
        if os.environ.get('NOTIFY_SLACK_ENABLED', '').lower() == 'true':
            self.slack_enabled = True
            self.slack_webhook = os.environ.get('NOTIFY_SLACK_WEBHOOK')
            print(f"✓ Slack notifications enabled from env")
    
    def create_html_email_body(self, result, plot_img=None):
        """Create beautiful HTML email with energy plot"""
        job_name = result['job_name']
        status = result['status']
        
        # Determine color scheme based on status
        if status == 'SUCCESS':
            status_color = '#28a745'
            status_emoji = '✅'
            status_text = 'Completed Successfully'
        elif status == 'TIMEOUT':
            status_color = '#ffc107'
            status_emoji = '⏰'
            status_text = 'Timed Out'
        elif status == 'FAILED':
            status_color = '#dc3545'
            status_emoji = '❌'
            status_text = 'Failed'
        else:
            status_color = '#6c757d'
            status_emoji = '⚠️'
            status_text = 'Error'
        
        # Build HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 30px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, {status_color} 0%, {status_color}dd 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px 8px 0 0;
                    margin: -30px -30px 30px -30px;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 600;
                }}
                .header .status {{
                    font-size: 18px;
                    margin-top: 10px;
                    opacity: 0.95;
                }}
                .section {{
                    margin-bottom: 25px;
                }}
                .section-title {{
                    font-size: 16px;
                    font-weight: 600;
                    color: #444;
                    margin-bottom: 12px;
                    padding-bottom: 8px;
                    border-bottom: 2px solid #e9ecef;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                tr {{
                    border-bottom: 1px solid #e9ecef;
                }}
                td {{
                    padding: 12px 8px;
                }}
                td:first-child {{
                    font-weight: 600;
                    color: #666;
                    width: 40%;
                }}
                td:last-child {{
                    color: #333;
                    font-family: 'Courier New', monospace;
                }}
                .success-value {{
                    color: #28a745;
                    font-weight: 600;
                }}
                .error-value {{
                    color: #dc3545;
                    font-weight: 600;
                }}
                .energy-box {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                    margin: 20px 0;
                }}
                .energy-box .value {{
                    font-size: 32px;
                    font-weight: 700;
                    margin: 10px 0;
                    font-family: 'Courier New', monospace;
                }}
                .energy-box .label {{
                    font-size: 14px;
                    opacity: 0.9;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .plot-container {{
                    text-align: center;
                    margin: 20px 0;
                    padding: 20px;
                    background-color: #f8f9fa;
                    border-radius: 8px;
                }}
                .plot-container img {{
                    max-width: 100%;
                    height: auto;
                    border-radius: 4px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 2px solid #e9ecef;
                    text-align: center;
                    color: #666;
                    font-size: 13px;
                }}
                .error-box {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{status_emoji} {job_name}</h1>
                    <div class="status">{status_text}</div>
                </div>
        """
        
        # Energy plot (if available)
        if plot_img:
            html += """
                <div class="section">
                    <div class="section-title">📊 Energy Evolution</div>
                    <div class="plot-container">
                        <img src="cid:energy_plot" alt="Energy vs Step Plot">
                    </div>
                </div>
            """
        
        # Job Information Section
        html += """
                <div class="section">
                    <div class="section-title">📋 Job Information</div>
                    <table>
        """
        
        html += f"""
                        <tr>
                            <td>Job Name</td>
                            <td>{result.get('job_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Input File</td>
                            <td>{result.get('job_file', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Output File</td>
                            <td>{result.get('output_file', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>OpenMP Threads</td>
                            <td>{result.get('num_cores', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Status</td>
                            <td class="{'success-value' if status == 'SUCCESS' else 'error-value'}">{status}</td>
                        </tr>
        """
        
        # Add structure files if present
        if result.get('cif_file'):
            html += f"""
                        <tr>
                            <td>Optimised Structure (CIF)</td>
                            <td>{result['cif_file']}</td>
                        </tr>
            """
        
        if result.get('plot_file'):
            html += f"""
                        <tr>
                            <td>Energy Plot</td>
                            <td>{result['plot_file']}</td>
                        </tr>
            """
        
        html += """
                    </table>
                </div>
        """
        
        # Timing Section
        elapsed_hours = result.get('elapsed_time_hours', 0)
        elapsed_sec = result.get('elapsed_time_sec', 0)
        wall_time_limit = result.get('wall_time_limit_hours', 'N/A')
        
        html += f"""
                <div class="section">
                    <div class="section-title">⏱️ Timing</div>
                    <table>
                        <tr>
                            <td>Elapsed Time</td>
                            <td><strong>{elapsed_hours:.4f}</strong> hours ({elapsed_sec:.2f} seconds)</td>
                        </tr>
                        <tr>
                            <td>Wall Time Limit</td>
                            <td>{wall_time_limit} hours</td>
                        </tr>
                        <tr>
                            <td>Completed At</td>
                            <td>{result.get('timestamp', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
        """
        
        # Energy and Convergence Section
        if result.get('total_energy') is not None or result.get('scf_converged') is not None:
            html += """
                <div class="section">
                    <div class="section-title">⚛️ Energy & Convergence</div>
            """
            
            if result.get('total_energy') is not None:
                html += f"""
                    <div class="energy-box">
                        <div class="label">Final Energy</div>
                        <div class="value">{result['total_energy']:.8f} Ha</div>
                    </div>
                """
            
            html += "<table>"
            
            if result.get('scf_converged') is not None:
                converged_text = "Yes ✓" if result['scf_converged'] else "No ✗"
                converged_class = "success-value" if result['scf_converged'] else "error-value"
                html += f"""
                        <tr>
                            <td>SCF Converged</td>
                            <td class="{converged_class}">{converged_text}</td>
                        </tr>
                """
            
            if result.get('num_scf_steps'):
                html += f"""
                        <tr>
                            <td>SCF Steps</td>
                            <td>{result['num_scf_steps']}</td>
                        </tr>
                """
            
            if result.get('total_force') is not None:
                html += f"""
                        <tr>
                            <td>Total Force</td>
                            <td>{result['total_force']:.8e}</td>
                        </tr>
                """
            
            # Add trajectory stats if available
            if result.get('trajectory_steps'):
                html += f"""
                        <tr>
                            <td>Trajectory Steps</td>
                            <td>{result['trajectory_steps']}</td>
                        </tr>
                """
            
            if result.get('energy_change'):
                html += f"""
                        <tr>
                            <td>Total Energy Change</td>
                            <td>{result['energy_change']:.8f} Ha</td>
                        </tr>
                """
            
            html += """
                    </table>
                </div>
            """
        
        # Error Section
        if result.get('error_message') or result.get('error'):
            error_msg = result.get('error_message') or result.get('error')
            html += f"""
                <div class="section">
                    <div class="section-title">⚠️ Error Information</div>
                    <div class="error-box">
                        <strong>Error:</strong> {error_msg}
                    </div>
                </div>
            """
        
        # Footer
        html += f"""
                <div class="footer">
                    CP2K Job Runner • Notification sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def send_email(self, subject, body, html=False, plot_img=None):
        """Send email notification with optional plot attachment"""
        if not self.email_enabled:
            return False
        
        try:
            msg = MIMEMultipart('related')  # 'related' for inline images
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            
            # Create alternative part for text/html
            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)
            
            if html:
                # Plain text version (fallback)
                text_part = MIMEText(self._html_to_text(body), 'plain')
                msg_alternative.attach(text_part)
                
                # HTML version
                html_part = MIMEText(body, 'html')
                msg_alternative.attach(html_part)
                
                # Attach plot as inline image
                if plot_img:
                    img_data = plot_img.read()
                    image = MIMEImage(img_data)
                    image.add_header('Content-ID', '<energy_plot>')
                    image.add_header('Content-Disposition', 'inline', filename='energy_plot.png')
                    msg.attach(image)
            else:
                msg_alternative.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
    
    def _html_to_text(self, html):
        """Convert HTML to plain text"""
        import re
        text = re.sub('<[^<]+?>', '', html)
        text = text.replace('&nbsp;', ' ')
        return text
    
    def send_teams(self, result):
        """Send Microsoft Teams notification"""
        if not self.teams_enabled:
            return False
        
        try:
            status = result['status']
            job_name = result['job_name']
            
            if status == 'SUCCESS':
                theme_color = '28a745'
                title = f"✅ Job Completed: {job_name}"
            elif status == 'TIMEOUT':
                theme_color = 'ffc107'
                title = f"⏰ Job Timed Out: {job_name}"
            elif status == 'FAILED':
                theme_color = 'dc3545'
                title = f"❌ Job Failed: {job_name}"
            else:
                theme_color = '6c757d'
                title = f"⚠️ Job Error: {job_name}"
            
            card = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "themeColor": theme_color,
                "title": title,
                "sections": [
                    {
                        "activityTitle": "Job Details",
                        "facts": [
                            {"name": "Status", "value": status},
                            {"name": "Elapsed Time", "value": f"{result.get('elapsed_time_hours', 0):.4f} hours"},
                            {"name": "Wall Time Limit", "value": f"{result.get('wall_time_limit_hours', 'N/A')} hours"},
                        ]
                    }
                ]
            }
            
            if result.get('total_energy') is not None:
                card["sections"].append({
                    "activityTitle": "Results",
                    "facts": [
                        {"name": "Final Energy", "value": f"{result['total_energy']:.8f} Ha"},
                        {"name": "SCF Converged", "value": "Yes ✓" if result.get('scf_converged') else "No ✗"},
                    ]
                })
                
                if result.get('trajectory_steps'):
                    card["sections"][-1]["facts"].append(
                        {"name": "Steps", "value": str(result['trajectory_steps'])}
                    )
            
            if result.get('cif_file'):
                card["sections"].append({
                    "activityTitle": "Output Files",
                    "facts": [
                        {"name": "Structure (CIF)", "value": result['cif_file']},
                        {"name": "Energy Plot", "value": result.get('plot_file', 'N/A')},
                    ]
                })
            
            if result.get('error_message') or result.get('error'):
                error_msg = result.get('error_message') or result.get('error')
                card["sections"].append({
                    "activityTitle": "⚠️ Error",
                    "text": error_msg
                })
            
            response = requests.post(self.teams_webhook, json=card)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Teams notification: {e}")
            return False
    
    def send_linework(self, result):
        """Send LINE Work notification"""
        if not self.linework_enabled:
            return False
        
        try:
            status = result['status']
            job_name = result['job_name']
            
            if status == 'SUCCESS':
                emoji = '✅'
            elif status == 'TIMEOUT':
                emoji = '⏰'
            elif status == 'FAILED':
                emoji = '❌'
            else:
                emoji = '⚠️'
            
            message = f"{emoji} Job {status}: {job_name}\n\n"
            message += f"📋 Details:\n"
            message += f"• Time: {result.get('elapsed_time_hours', 0):.4f} hours\n"
            
            if result.get('total_energy') is not None:
                message += f"\n⚛️ Results:\n"
                message += f"• Energy: {result['total_energy']:.8f} Ha\n"
                message += f"• Converged: {'Yes ✓' if result.get('scf_converged') else 'No ✗'}\n"
                if result.get('trajectory_steps'):
                    message += f"• Steps: {result['trajectory_steps']}\n"
            
            if result.get('cif_file'):
                message += f"\n📁 Files:\n"
                message += f"• Structure: {result['cif_file']}\n"
                message += f"• Plot: {result.get('plot_file', 'N/A')}\n"
            
            if result.get('error_message') or result.get('error'):
                error_msg = result.get('error_message') or result.get('error')
                message += f"\n⚠️ Error: {error_msg}\n"
            
            payload = {"content": message}
            response = requests.post(self.linework_webhook, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send LINE Work notification: {e}")
            return False
    
    def send_slack(self, result):
        """Send Slack notification with rich formatting"""
        if not self.slack_enabled:
            return False
        
        try:
            status = result['status']
            job_name = result['job_name']
            
            # Determine emoji and color
            if status == 'SUCCESS':
                emoji = '✅'
                color = 'good'  # green
            elif status == 'TIMEOUT':
                emoji = '⏰'
                color = 'warning'  # yellow
            elif status == 'FAILED':
                emoji = '❌'
                color = 'danger'  # red
            else:
                emoji = '⚠️'
                color = '#6c757d'  # gray
            
            # Build Slack message with blocks for rich formatting
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} Job {status}: {job_name}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Status:*\n{status}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Elapsed Time:*\n{result.get('elapsed_time_hours', 0):.4f} hours"
                        }
                    ]
                }
            ]
            
            # Add energy info if available
            if result.get('total_energy') is not None:
                energy_fields = [
                    {
                        "type": "mrkdwn",
                        "text": f"*Final Energy:*\n{result['total_energy']:.8f} Ha"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*SCF Converged:*\n{'Yes ✓' if result.get('scf_converged') else 'No ✗'}"
                    }
                ]
                
                if result.get('trajectory_steps'):
                    energy_fields.append({
                        "type": "mrkdwn",
                        "text": f"*Trajectory Steps:*\n{result['trajectory_steps']}"
                    })
                
                if result.get('energy_change'):
                    energy_fields.append({
                        "type": "mrkdwn",
                        "text": f"*Energy Change:*\n{result['energy_change']:.8f} Ha"
                    })
                
                blocks.append({
                    "type": "section",
                    "fields": energy_fields
                })
            
            # Add file info if available
            if result.get('plot_file') or result.get('cif_file'):
                file_text = "*Output Files:*\n"
                if result.get('plot_file'):
                    file_text += f"📊 Energy Plot: `{Path(result['plot_file']).name}`\n"
                if result.get('cif_file'):
                    file_text += f"💎 Structure CIF: `{Path(result['cif_file']).name}`"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": file_text
                    }
                })
            
            # Add error info if present
            if result.get('error_message') or result.get('error'):
                error_msg = result.get('error_message') or result.get('error')
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *Error:*\n```{error_msg}```"
                    }
                })
            
            # Add context with timestamp
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Completed at {result.get('timestamp', 'N/A')}"
                    }
                ]
            })
            
            # Send to Slack
            payload = {
                "blocks": blocks,
                "attachments": [{
                    "color": color,
                    "fallback": f"Job {status}: {job_name}"
                }]
            }
            
            response = requests.post(self.slack_webhook, json=payload)
            return response.status_code == 200
            
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False
    
    def notify_job_complete(self, result, plot_img=None):
        """Notify when a job completes"""
        job_name = result['job_name']
        status = result['status']
        
        if self.email_enabled:
            if status == 'SUCCESS':
                subject = f"✅ CP2K Job Completed: {job_name}"
            elif status == 'TIMEOUT':
                subject = f"⏰ CP2K Job Timed Out: {job_name}"
            elif status == 'FAILED':
                subject = f"❌ CP2K Job Failed: {job_name}"
            else:
                subject = f"⚠️ CP2K Job Error: {job_name}"
            
            html_body = self.create_html_email_body(result, plot_img)
            self.send_email(subject, html_body, html=True, plot_img=plot_img)
            print(f"  📧 Email notification sent")
        
        if self.teams_enabled:
            self.send_teams(result)
            print(f"  💬 Teams notification sent")
        
        if self.linework_enabled:
            self.send_linework(result)
            print(f"  📱 LINE Work notification sent")
        
        if self.slack_enabled:
            self.send_slack(result)
            print(f"  💬 Slack notification sent")
    
    def notify_queue_complete(self, summary):
        """Notify when entire queue completes"""
        subject = f"🏁 CP2K Queue Complete - {summary['total']} jobs finished"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 30px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px 8px 0 0;
                    margin: -30px -30px 30px -30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 600;
                }}
                .stats {{
                    display: flex;
                    justify-content: space-around;
                    margin: 30px 0;
                    flex-wrap: wrap;
                }}
                .stat-box {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                    min-width: 120px;
                    margin: 10px;
                    border-left: 4px solid #667eea;
                }}
                .stat-box .value {{
                    font-size: 36px;
                    font-weight: 700;
                    color: #667eea;
                }}
                .stat-box .label {{
                    font-size: 14px;
                    color: #666;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    margin-top: 8px;
                }}
                .success {{ border-left-color: #28a745; }}
                .success .value {{ color: #28a745; }}
                .failed {{ border-left-color: #dc3545; }}
                .failed .value {{ color: #dc3545; }}
                .timeout {{ border-left-color: #ffc107; }}
                .timeout .value {{ color: #ffc107; }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                tr {{
                    border-bottom: 1px solid #e9ecef;
                }}
                td {{
                    padding: 12px 8px;
                }}
                td:first-child {{
                    font-weight: 600;
                    color: #666;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 2px solid #e9ecef;
                    text-align: center;
                    color: #666;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏁 All CP2K Jobs Completed!</h1>
                </div>
                
                <div class="stats">
                    <div class="stat-box">
                        <div class="value">{summary['total']}</div>
                        <div class="label">Total Jobs</div>
                    </div>
                    <div class="stat-box success">
                        <div class="value">{summary['success']}</div>
                        <div class="label">Successful</div>
                    </div>
                    <div class="stat-box failed">
                        <div class="value">{summary['failed']}</div>
                        <div class="label">Failed</div>
                    </div>
                    <div class="stat-box timeout">
                        <div class="value">{summary['timeout']}</div>
                        <div class="label">Timed Out</div>
                    </div>
                </div>
                
                <table>
                    <tr>
                        <td>Total Runtime</td>
                        <td><strong>{summary['total_time_hours']:.2f}</strong> hours</td>
                    </tr>
                    <tr>
                        <td>Average per Job</td>
                        <td><strong>{summary['avg_time_hours']:.4f}</strong> hours</td>
                    </tr>
                    <tr>
                        <td>Results File</td>
                        <td>{summary['output_csv']}</td>
                    </tr>
                </table>
                
                <div class="footer">
                    CP2K Job Runner • Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        self.send_email(subject, html, html=True)
        
        if self.teams_enabled:
            card = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "themeColor": "667eea",
                "title": f"🏁 Queue Complete: {summary['total']} jobs",
                "sections": [{
                    "facts": [
                        {"name": "Total Jobs", "value": str(summary['total'])},
                        {"name": "✅ Successful", "value": str(summary['success'])},
                        {"name": "❌ Failed", "value": str(summary['failed'])},
                        {"name": "⏰ Timed Out", "value": str(summary['timeout'])},
                        {"name": "Total Time", "value": f"{summary['total_time_hours']:.2f} hours"},
                    ]
                }]
            }
            requests.post(self.teams_webhook, json=card)
        
        if self.linework_enabled:
            message = f"🏁 All {summary['total']} CP2K jobs completed!\n\n"
            message += f"✅ Successful: {summary['success']}\n"
            message += f"❌ Failed: {summary['failed']}\n"
            message += f"⏰ Timed Out: {summary['timeout']}\n"
            message += f"\n⏱️ Total Time: {summary['total_time_hours']:.2f} hours"
            payload = {"content": message}
            requests.post(self.linework_webhook, json=payload)
        
        if self.slack_enabled:
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
                        {"type": "mrkdwn", "text": f"*Total Jobs:*\n{summary['total']}"},
                        {"type": "mrkdwn", "text": f"*✅ Successful:*\n{summary['success']}"},
                        {"type": "mrkdwn", "text": f"*❌ Failed:*\n{summary['failed']}"},
                        {"type": "mrkdwn", "text": f"*⏰ Timed Out:*\n{summary['timeout']}"},
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Total Time:*\n{summary['total_time_hours']:.2f} hours"},
                        {"type": "mrkdwn", "text": f"*Average:*\n{summary['avg_time_hours']:.4f} hours/job"},
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Results saved to: `{summary['output_csv']}`"}
                    ]
                }
            ]
            payload = {
                "blocks": blocks,
                "attachments": [{"color": "good"}]
            }
            requests.post(self.slack_webhook, json=payload)
    
    def notify_crash(self, error_type, error_message, traceback_info, job_info=None):
        """Send emergency notification when script crashes unexpectedly"""
        print("\n" + "="*60)
        print("🚨 EMERGENCY: Script crashed unexpectedly!")
        print("="*60)
        print(f"Error Type: {error_type}")
        print(f"Error Message: {error_message}")
        print(f"Traceback:\n{traceback_info}")
        print("="*60)
        print("Attempting to send crash notification...")
        
        # Try Slack first (most reliable, no authentication)
        if self.slack_enabled:
            try:
                blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "🚨 CP2K Job Runner CRASHED!",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*The job runner script crashed unexpectedly!*\n\nThis requires your immediate attention."
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Error Type:*\n`{error_type}`"},
                            {"type": "mrkdwn", "text": f"*Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Error Message:*\n```{error_message[:500]}```"
                        }
                    }
                ]
                
                if job_info:
                    blocks.append({
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Last Job:*\n{job_info.get('job_name', 'Unknown')}"},
                            {"type": "mrkdwn", "text": f"*Jobs Completed:*\n{job_info.get('completed', 0)}/{job_info.get('total', 0)}"},
                        ]
                    })
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Full Traceback:*\n```{traceback_info[:1000]}```"
                    }
                })
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*What to do:*\n1. Check the terminal/log for full error\n2. Restart the script\n3. Check if results were saved to CSV"
                    }
                })
                
                payload = {
                    "blocks": blocks,
                    "attachments": [{"color": "danger"}]
                }
                
                response = requests.post(self.slack_webhook, json=payload, timeout=10)
                if response.status_code == 200:
                    print("✓ Slack crash notification sent!")
                else:
                    print(f"✗ Slack notification failed: {response.status_code}")
            except Exception as e:
                print(f"✗ Failed to send Slack crash notification: {e}")
        
        # Try email
        if self.email_enabled:
            try:
                subject = "🚨 CP2K Job Runner CRASHED!"
                body = f"""
EMERGENCY: CP2K Job Runner Script Crashed

The job runner script has crashed unexpectedly and requires your attention.

Error Type: {error_type}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Error Message:
{error_message}

"""
                if job_info:
                    body += f"""
Last Job Processing: {job_info.get('job_name', 'Unknown')}
Jobs Completed: {job_info.get('completed', 0)}/{job_info.get('total', 0)}

"""
                
                body += f"""
Full Traceback:
{traceback_info}

What to do:
1. Check the terminal/log for full error details
2. Restart the script to resume processing
3. Check if results were saved to CSV
4. Fix any environment issues (e.g., VSCode changing Python env)

Results may be partially saved to the output CSV.
"""
                
                self.send_email(subject, body, html=False)
                print("✓ Email crash notification sent!")
            except Exception as e:
                print(f"✗ Failed to send email crash notification: {e}")
        
        # Try Teams
        if self.teams_enabled:
            try:
                card = {
                    "@type": "MessageCard",
                    "@context": "https://schema.org/extensions",
                    "themeColor": "dc3545",
                    "title": "🚨 CP2K Job Runner CRASHED!",
                    "sections": [
                        {
                            "activityTitle": "Script Crash - Immediate Attention Required",
                            "facts": [
                                {"name": "Error Type", "value": error_type},
                                {"name": "Time", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                                {"name": "Error", "value": error_message[:200]},
                            ]
                        }
                    ]
                }
                if job_info:
                    card["sections"][0]["facts"].append({
                        "name": "Progress", 
                        "value": f"{job_info.get('completed', 0)}/{job_info.get('total', 0)} jobs"
                    })
                
                requests.post(self.teams_webhook, json=card, timeout=10)
                print("✓ Teams crash notification sent!")
            except Exception as e:
                print(f"✗ Failed to send Teams crash notification: {e}")
        
        # Try LINE Work
        if self.linework_enabled:
            try:
                message = f"🚨 CP2K Job Runner CRASHED!\n\n"
                message += f"Error: {error_type}\n"
                message += f"Message: {error_message[:200]}\n"
                message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                message += "Check terminal for full details!"
                
                payload = {"content": message}
                requests.post(self.linework_webhook, json=payload, timeout=10)
                print("✓ LINE Work crash notification sent!")
            except Exception as e:
                print(f"✗ Failed to send LINE Work crash notification: {e}")
        """Notify when entire queue completes"""
        subject = f"🏁 CP2K Queue Complete - {summary['total']} jobs finished"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 30px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px 8px 0 0;
                    margin: -30px -30px 30px -30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 600;
                }}
                .stats {{
                    display: flex;
                    justify-content: space-around;
                    margin: 30px 0;
                    flex-wrap: wrap;
                }}
                .stat-box {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                    min-width: 120px;
                    margin: 10px;
                    border-left: 4px solid #667eea;
                }}
                .stat-box .value {{
                    font-size: 36px;
                    font-weight: 700;
                    color: #667eea;
                }}
                .stat-box .label {{
                    font-size: 14px;
                    color: #666;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    margin-top: 8px;
                }}
                .success {{ border-left-color: #28a745; }}
                .success .value {{ color: #28a745; }}
                .failed {{ border-left-color: #dc3545; }}
                .failed .value {{ color: #dc3545; }}
                .timeout {{ border-left-color: #ffc107; }}
                .timeout .value {{ color: #ffc107; }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                tr {{
                    border-bottom: 1px solid #e9ecef;
                }}
                td {{
                    padding: 12px 8px;
                }}
                td:first-child {{
                    font-weight: 600;
                    color: #666;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 2px solid #e9ecef;
                    text-align: center;
                    color: #666;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏁 All CP2K Jobs Completed!</h1>
                </div>
                
                <div class="stats">
                    <div class="stat-box">
                        <div class="value">{summary['total']}</div>
                        <div class="label">Total Jobs</div>
                    </div>
                    <div class="stat-box success">
                        <div class="value">{summary['success']}</div>
                        <div class="label">Successful</div>
                    </div>
                    <div class="stat-box failed">
                        <div class="value">{summary['failed']}</div>
                        <div class="label">Failed</div>
                    </div>
                    <div class="stat-box timeout">
                        <div class="value">{summary['timeout']}</div>
                        <div class="label">Timed Out</div>
                    </div>
                </div>
                
                <table>
                    <tr>
                        <td>Total Runtime</td>
                        <td><strong>{summary['total_time_hours']:.2f}</strong> hours</td>
                    </tr>
                    <tr>
                        <td>Average per Job</td>
                        <td><strong>{summary['avg_time_hours']:.4f}</strong> hours</td>
                    </tr>
                    <tr>
                        <td>Results File</td>
                        <td>{summary['output_csv']}</td>
                    </tr>
                </table>
                
                <div class="footer">
                    CP2K Job Runner • Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        self.send_email(subject, html, html=True)
        
        if self.teams_enabled:
            card = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "themeColor": "667eea",
                "title": f"🏁 Queue Complete: {summary['total']} jobs",
                "sections": [{
                    "facts": [
                        {"name": "Total Jobs", "value": str(summary['total'])},
                        {"name": "✅ Successful", "value": str(summary['success'])},
                        {"name": "❌ Failed", "value": str(summary['failed'])},
                        {"name": "⏰ Timed Out", "value": str(summary['timeout'])},
                        {"name": "Total Time", "value": f"{summary['total_time_hours']:.2f} hours"},
                    ]
                }]
            }
            requests.post(self.teams_webhook, json=card)
        
        if self.linework_enabled:
            message = f"🏁 All {summary['total']} CP2K jobs completed!\n\n"
            message += f"✅ Successful: {summary['success']}\n"
            message += f"❌ Failed: {summary['failed']}\n"
            message += f"⏰ Timed Out: {summary['timeout']}\n"
            message += f"\n⏱️ Total Time: {summary['total_time_hours']:.2f} hours"
            payload = {"content": message}
            requests.post(self.linework_webhook, json=payload)
        
        if self.slack_enabled:
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
                        {"type": "mrkdwn", "text": f"*Total Jobs:*\n{summary['total']}"},
                        {"type": "mrkdwn", "text": f"*✅ Successful:*\n{summary['success']}"},
                        {"type": "mrkdwn", "text": f"*❌ Failed:*\n{summary['failed']}"},
                        {"type": "mrkdwn", "text": f"*⏰ Timed Out:*\n{summary['timeout']}"},
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Total Time:*\n{summary['total_time_hours']:.2f} hours"},
                        {"type": "mrkdwn", "text": f"*Average:*\n{summary['avg_time_hours']:.4f} hours/job"},
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Results saved to: `{summary['output_csv']}`"}
                    ]
                }
            ]
            payload = {
                "blocks": blocks,
                "attachments": [{"color": "good"}]
            }
            requests.post(self.slack_webhook, json=payload)


class CP2KJobRunner:
    def __init__(self, input_csv, output_csv="cp2k_results.csv", cp2k_executable="cp2k.psmp", 
                 wall_time_hours=12, notify_config=None, notify_mode='complete'):
        """Initialize the CP2K job runner"""
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.cp2k_executable = cp2k_executable
        self.wall_time_hours = wall_time_hours
        self.wall_time_seconds = int(wall_time_hours * 3600)
        self.results = []
        
        self.notifier = Notifier(notify_config, notify_mode)
        self._verify_cp2k()
        
    def _verify_cp2k(self):
        """Check if CP2K executable is available"""
        try:
            result = subprocess.run(
                [self.cp2k_executable, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✓ Found CP2K: {self.cp2k_executable}")
                version_match = re.search(r'CP2K version (\S+)', result.stdout)
                if version_match:
                    print(f"  Version: {version_match.group(1)}")
        except FileNotFoundError:
            print(f"ERROR: CP2K executable '{self.cp2k_executable}' not found!")
            sys.exit(1)
        except Exception as e:
            print(f"Warning: Could not verify CP2K: {e}")
    
    def read_jobs(self):
        """Read job specifications from CSV"""
        try:
            df = pd.read_csv(self.input_csv)
            required_cols = ['job_file', 'num_cores']
            
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")
            
            if 'wall_time_hours' not in df.columns:
                df['wall_time_hours'] = self.wall_time_hours
            
            return df
        except Exception as e:
            print(f"Error reading input CSV: {e}")
            sys.exit(1)
    
    def parse_cp2k_output(self, output_file):
        """Parse CP2K output file to extract key results"""
        results = {
            'total_energy': None,
            'scf_converged': False,
            'num_scf_steps': None,
            'total_force': None,
            'wall_time': None,
            'cpu_time': None,
            'error_message': None
        }
        
        if not os.path.exists(output_file):
            results['error_message'] = "Output file not found"
            return results
        
        try:
            with open(output_file, 'r') as f:
                content = f.read()
                
                if "PROGRAM ENDED AT" in content:
                    results['scf_converged'] = True
                
                energy_matches = re.findall(r'ENERGY\| Total FORCE_EVAL.*?:\s+([-\d.]+)', content)
                if energy_matches:
                    results['total_energy'] = float(energy_matches[-1])
                
                if results['total_energy'] is None:
                    energy_matches = re.findall(r'Total energy:\s+([-\d.]+)', content)
                    if energy_matches:
                        results['total_energy'] = float(energy_matches[-1])
                
                scf_matches = re.findall(r'SCF run converged in\s+(\d+)\s+steps', content)
                if scf_matches:
                    results['num_scf_steps'] = int(scf_matches[-1])
                
                force_matches = re.findall(r'SUM OF ATOMIC FORCES\s+([-\d.E+]+)', content)
                if force_matches:
                    results['total_force'] = float(force_matches[-1])
                
                wall_time_matches = re.findall(r'CP2K.*?(\d+\.\d+)\s+seconds', content)
                if wall_time_matches:
                    results['wall_time'] = float(wall_time_matches[-1])
                
                if "ABORT" in content or "ERROR" in content:
                    error_lines = [line.strip() for line in content.split('\n') 
                                   if 'ERROR' in line or 'ABORT' in line]
                    if error_lines:
                        results['error_message'] = error_lines[0][:200]
                        results['scf_converged'] = False
                
                if "exceeded the maximum number of steps" in content:
                    results['error_message'] = "SCF did not converge (max steps exceeded)"
                    results['scf_converged'] = False
                        
        except Exception as e:
            results['error_message'] = f"Error parsing output: {str(e)}"
        
        return results
    
    def process_trajectory_and_structure(self, job_path, job_name, input_file):
        """
        Process trajectory file to generate plot and export CIF
        
        Returns:
            dict: {
                'plot_file': path to energy plot,
                'cif_file': path to CIF structure,
                'trajectory_steps': number of steps,
                'energy_change': total energy change,
                'plot_img': BytesIO object with plot for email
            }
        """
        result = {
            'plot_file': None,
            'cif_file': None,
            'trajectory_steps': None,
            'energy_change': None,
            'plot_img': None
        }
        
        # Get PROJECT_NAME from input file (CP2K uses this for output names)
        project_name = StructureHandler.get_project_name(input_file)
        
        if project_name:
            # Try PROJECT_NAME-pos-1.xyz first
            xyz_file = job_path / f"{project_name}-pos-1.xyz"
            print(f"  🔍 Looking for trajectory: {xyz_file}")
        else:
            # Fallback to job_name
            xyz_file = job_path / f"{job_name}-pos-1.xyz"
            print(f"  🔍 Looking for trajectory (fallback): {xyz_file}")
        
        # Also try common alternative names
        if not xyz_file.exists():
            alternatives = [
                job_path / f"{job_name}-pos-1.xyz",
                job_path / "pos-1.xyz",
                job_path / f"{project_name}-pos-1.xyz" if project_name else None,
            ]
            
            for alt in alternatives:
                if alt and alt.exists():
                    xyz_file = alt
                    print(f"  ✓ Found trajectory: {xyz_file}")
                    break
        
        if not xyz_file.exists():
            print(f"  ℹ️  No trajectory file found")
            print(f"     Tried: {job_name}-pos-1.xyz")
            if project_name:
                print(f"     Tried: {project_name}-pos-1.xyz")
            print(f"     Tried: pos-1.xyz")
            return result
        
        print(f"  📂 Processing trajectory: {xyz_file}")
        
        # Parse trajectory
        traj_data = StructureHandler.parse_xyz_trajectory(xyz_file)
        
        if not traj_data:
            print(f"  ⚠️  Could not parse trajectory file")
            return result
        
        energies = traj_data['energies']
        steps = traj_data['steps']
        structures = traj_data['structures']
        
        result['trajectory_steps'] = len(steps)
        result['energy_change'] = energies[-1] - energies[0] if len(energies) > 1 else 0
        
        print(f"  ✓ Trajectory: {len(steps)} steps")
        print(f"  ✓ Energy change: {result['energy_change']:.8f} Ha")
        
        # Use job_name for output files (for consistency)
        # Generate energy plot
        plot_file = job_path / f"{job_name}_energy_plot.png"
        plot_img = EnergyPlotter.create_energy_plot(
            energies, steps, job_name, str(plot_file)
        )
        
        if plot_img:
            result['plot_file'] = str(plot_file)
            result['plot_img'] = plot_img
        
        # Export final structure to CIF
        if structures:
            # Get cell parameters from input file
            cell = StructureHandler.parse_cell_from_input(input_file)
            
            if cell:
                cif_file = job_path / f"{job_name}_optimised_structure.cif"
                final_structure = structures[-1]
                
                if StructureHandler.write_cif(final_structure, cell, str(cif_file)):
                    result['cif_file'] = str(cif_file)
                    print(f"  💾 Structure saved: {cif_file}")
            else:
                print(f"  ⚠️  Could not extract cell parameters from input file")
        
        return result
    
    def run_cp2k_job(self, job_file, num_cores, job_name=None, wall_time_hours=None, 
                     job_num=None, total_jobs=None):
        """Run a single CP2K job"""
        if not os.path.exists(job_file):
            return {
                'job_file': job_file,
                'status': 'FAILED',
                'error': 'Input file not found'
            }
        
        if wall_time_hours is None:
            wall_time_hours = self.wall_time_hours
        wall_time_seconds = int(wall_time_hours * 3600)
        
        job_path = Path(job_file).parent
        if job_name is None:
            job_name = Path(job_file).stem
        
        output_file = job_path / f"{job_name}.out"
        
        cmd = [
            self.cp2k_executable,
            '-i', str(job_file),
            '-o', str(output_file)
        ]
        
        env = os.environ.copy()
        env['OMP_NUM_THREADS'] = str(num_cores)
        env['OMP_PROC_BIND'] = 'close'
        env['OMP_PLACES'] = 'cores'
        env['OMP_DYNAMIC'] = 'FALSE'
        
        print(f"\n{'='*60}")
        print(f"Starting job: {job_name} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if job_num and total_jobs:
            print(f"Progress: [{job_num}/{total_jobs}]")
        print(f"Input file: {job_file}")
        print(f"Output file: {output_file}")
        print(f"OpenMP threads: {num_cores}")
        print(f"Command: {' '.join(cmd)}")
        print(f"Environment: OMP_NUM_THREADS={num_cores}")
        print(f"Wall time limit: {wall_time_hours} hours")
        print(f"{'='*60}\n")
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=wall_time_seconds,
                cwd=str(job_path)
            )
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            parsed_results = self.parse_cp2k_output(output_file)
            
            # Process trajectory and generate plot/CIF
            traj_results = self.process_trajectory_and_structure(job_path, job_name, job_file)
            
            job_result = {
                'job_name': job_name,
                'job_file': str(job_file),
                'num_cores': num_cores,
                'wall_time_limit_hours': wall_time_hours,
                'status': 'SUCCESS' if result.returncode == 0 else 'FAILED',
                'return_code': result.returncode,
                'elapsed_time_sec': round(elapsed, 2),
                'elapsed_time_hours': round(elapsed / 3600, 4),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'output_file': str(output_file),
                **parsed_results,
                **{k: v for k, v in traj_results.items() if k != 'plot_img'}
            }
            
            print(f"\n✓ Job {job_name} completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Status: {job_result['status']}")
            print(f"  Time: {elapsed/3600:.4f} hours")
            if parsed_results['total_energy']:
                print(f"  Energy: {parsed_results['total_energy']:.8f} Ha")
            
            # Send notification with plot
            self.notifier.notify_job_complete(job_result, traj_results.get('plot_img'))
            
            return job_result
            
        except subprocess.TimeoutExpired:
            end_time = time.time()
            elapsed = end_time - start_time
            
            print(f"\n⚠ Job {job_name} TIMED OUT at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            parsed_results = self.parse_cp2k_output(output_file)
            traj_results = self.process_trajectory_and_structure(job_path, job_name, job_file)
            
            job_result = {
                'job_name': job_name,
                'job_file': str(job_file),
                'num_cores': num_cores,
                'wall_time_limit_hours': wall_time_hours,
                'status': 'TIMEOUT',
                'return_code': -1,
                'elapsed_time_sec': round(elapsed, 2),
                'elapsed_time_hours': round(elapsed / 3600, 4),
                'error': f'Job exceeded wall time limit of {wall_time_hours} hours',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'output_file': str(output_file),
                **parsed_results,
                **{k: v for k, v in traj_results.items() if k != 'plot_img'}
            }
            
            self.notifier.notify_job_complete(job_result, traj_results.get('plot_img'))
            
            return job_result
            
        except Exception as e:
            end_time = time.time()
            elapsed = end_time - start_time
            
            job_result = {
                'job_name': job_name,
                'job_file': str(job_file),
                'num_cores': num_cores,
                'wall_time_limit_hours': wall_time_hours,
                'status': 'ERROR',
                'elapsed_time_sec': round(elapsed, 2),
                'elapsed_time_hours': round(elapsed / 3600, 4),
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            self.notifier.notify_job_complete(job_result)
            
            return job_result
    
    def run_all_jobs(self, live_reload=True):
        """Run all jobs from the input CSV with crash protection"""
        jobs_df = self.read_jobs()
        initial_job_count = len(jobs_df)
        
        print(f"\n{'='*60}")
        print(f"CP2K Job Runner")
        print(f"{'='*60}")
        print(f"Total jobs: {initial_job_count}")
        print(f"Features: Energy plots + CIF export")
        print(f"Crash protection: ENABLED")
        print(f"{'='*60}\n")
        
        job_idx = 0
        
        try:
            while job_idx < initial_job_count:
                if live_reload:
                    try:
                        jobs_df = self.read_jobs()
                    except:
                        pass
                
                row = jobs_df.iloc[job_idx]
                
                job_file = row['job_file']
                num_cores = int(row['num_cores'])
                job_name = row.get('job_name', None)
                wall_time_hours = row.get('wall_time_hours', self.wall_time_hours)
                
                try:
                    result = self.run_cp2k_job(job_file, num_cores, job_name, wall_time_hours,
                                              job_idx+1, len(jobs_df))
                    self.results.append(result)
                    self.save_results()
                except Exception as job_error:
                    # Job-specific error (don't crash the whole queue)
                    print(f"\n⚠️ Error running job {job_name}: {job_error}")
                    error_result = {
                        'job_name': job_name or 'unknown',
                        'job_file': str(job_file),
                        'status': 'ERROR',
                        'error': str(job_error),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    self.results.append(error_result)
                    self.save_results()
                    
                    # Notify about this specific job error
                    try:
                        self.notifier.notify_job_complete(error_result)
                    except:
                        pass
                
                job_idx += 1
            
            # All jobs completed normally
            print(f"\n{'='*60}")
            print(f"All jobs completed!")
            print(f"{'='*60}\n")
            
            summary = self.print_summary()
            self.notifier.notify_queue_complete(summary)
            
        except KeyboardInterrupt:
            # User pressed Ctrl+C
            print("\n" + "="*60)
            print("⚠️ Queue interrupted by user (Ctrl+C)")
            print("="*60)
            print(f"Jobs completed: {job_idx}/{initial_job_count}")
            print(f"Results saved to: {self.output_csv}")
            
            # Send interruption notification
            try:
                self.notifier.notify_crash(
                    "KeyboardInterrupt",
                    "User manually stopped the job queue (Ctrl+C)",
                    "Queue was interrupted by user",
                    {
                        'job_name': job_name if job_idx < initial_job_count else 'None',
                        'completed': job_idx,
                        'total': initial_job_count
                    }
                )
            except:
                pass
            
            raise  # Re-raise to exit
            
        except Exception as e:
            # Unexpected crash!
            import traceback
            tb = traceback.format_exc()
            
            print("\n" + "="*60)
            print("🚨 FATAL ERROR: Script crashed unexpectedly!")
            print("="*60)
            print(f"Error: {type(e).__name__}")
            print(f"Message: {str(e)}")
            print(f"\nFull traceback:\n{tb}")
            print("="*60)
            print(f"Jobs completed before crash: {job_idx}/{initial_job_count}")
            print(f"Partial results saved to: {self.output_csv}")
            print("="*60)
            
            # Send crash notification
            try:
                current_job = job_name if job_idx < initial_job_count else 'Unknown'
                self.notifier.notify_crash(
                    type(e).__name__,
                    str(e),
                    tb,
                    {
                        'job_name': current_job,
                        'completed': job_idx,
                        'total': initial_job_count
                    }
                )
            except Exception as notify_error:
                print(f"\n⚠️ Could not send crash notification: {notify_error}")
            
            raise  # Re-raise to show full error
    
    def print_summary(self):
        """Print summary of all jobs"""
        df = pd.DataFrame(self.results)
        
        summary = {
            'total': len(df),
            'success': len(df[df['status'] == 'SUCCESS']),
            'failed': len(df[df['status'] == 'FAILED']),
            'timeout': len(df[df['status'] == 'TIMEOUT']),
            'error': len(df[df['status'] == 'ERROR']),
            'total_time_sec': 0,
            'total_time_hours': 0,
            'avg_time_hours': 0,
            'output_csv': self.output_csv
        }
        
        print("\nJob Summary:")
        print(f"  Total: {summary['total']}")
        print(f"  ✅ Success: {summary['success']}")
        print(f"  ❌ Failed: {summary['failed']}")
        print(f"  ⏰ Timeout: {summary['timeout']}")
        
        if 'elapsed_time_sec' in df.columns:
            summary['total_time_sec'] = df['elapsed_time_sec'].sum()
            summary['total_time_hours'] = summary['total_time_sec'] / 3600
            summary['avg_time_hours'] = df['elapsed_time_sec'].mean() / 3600
            
            print(f"  ⏱️  Total: {summary['total_time_hours']:.2f} hours")
            print(f"  ⏱️  Avg: {summary['avg_time_hours']:.4f} hours/job")
        
        return summary
    
    def save_results(self):
        """Save results to CSV"""
        results_df = pd.DataFrame(self.results)
        results_df.to_csv(self.output_csv, index=False)


def create_example_notification_config(filename="notification_config.json"):
    """Create example notification configuration"""
    config = {
        "email": {
            "enabled": False,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "sender_email": "your_email@gmail.com",
            "sender_password": "your_app_password_here",
            "recipient_email": "your_email@gmail.com"
        },
        "slack": {
            "enabled": False,
            "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
        },
        "teams": {
            "enabled": False,
            "webhook_url": "https://outlook.office.com/webhook/YOUR_WEBHOOK_URL"
        },
        "linework": {
            "enabled": False,
            "webhook_url": "https://works-webhook.linecorp.com/YOUR_WEBHOOK_URL"
        }
    }
    
    with open(filename, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Created: {filename}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("CP2K Job Runner - Final Version")
        print("="*60)
        print("\nFeatures:")
        print("  ✓ Beautiful HTML email notifications")
        print("  ✓ Energy vs step plots (from pos-1.xyz)")
        print("  ✓ CIF structure export (optimised_structure.cif)")
        print("  ✓ Teams & LINE Work support")
        print("\nUsage: python cp2k_job_runner_final.py <input_csv> [options]")
        print("\nOptions:")
        print("  --output <file>          : Output CSV")
        print("  --executable <path>      : CP2K binary")
        print("  --walltime <hours>       : Wall time limit")
        print("  --notify-config <file>   : Notification config")
        print("  --no-live-reload         : Disable CSV reload")
        print("  --create-notify-config   : Create example config")
        sys.exit(1)
    
    if sys.argv[1] == "--create-notify-config":
        create_example_notification_config()
        sys.exit(0)
    
    # Parse arguments
    input_csv = sys.argv[1]
    output_csv = "cp2k_results.csv"
    cp2k_exec = "cp2k.ssmp"
    wall_time_hours = 12.0
    live_reload = True
    notify_config = None
    
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--output' and i+1 < len(sys.argv):
            output_csv = sys.argv[i+1]
            i += 2
        elif arg == '--executable' and i+1 < len(sys.argv):
            cp2k_exec = sys.argv[i+1]
            i += 2
        elif arg == '--walltime' and i+1 < len(sys.argv):
            wall_time_hours = float(sys.argv[i+1])
            i += 2
        elif arg == '--notify-config' and i+1 < len(sys.argv):
            notify_config = sys.argv[i+1]
            i += 2
        elif arg == '--no-live-reload':
            live_reload = False
            i += 1
        else:
            i += 1
    
    if not os.path.exists(input_csv):
        print(f"ERROR: Input CSV not found: {input_csv}")
        sys.exit(1)
    
    print("\nInitializing CP2K Job Runner (Final Version)...")
    runner = CP2KJobRunner(input_csv, output_csv, cp2k_exec, wall_time_hours, notify_config)
    runner.run_all_jobs(live_reload=live_reload)
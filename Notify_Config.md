# Setup Guide: Teams & LINE Work with Beautiful HTML Emails

## Perfect for Your Use Case!

Since you have 15 jobs that take 8-24 hours each, this setup will:
- ✅ **Only notify when each job completes** (no spam!)
- ✅ **Send beautiful HTML emails** with full results
- ✅ **Support Microsoft Teams** instead of Slack
- ✅ **Support LINE Work** (Linework)
- ✅ **Final summary** when all 15 jobs finish

---

## Quick Start (5 Minutes)

### Option 1: Gmail with HTML Emails (Recommended)

#### Step 1: Get Gmail App Password
1. Go to https://myaccount.google.com/apppasswords
2. Create app password named "CP2K"
3. Copy the 16-character password

#### Step 2: Create & Edit Config
```bash
python cp2k_job_runner_final.py --create-notify-config
```

Edit `notification_config.json`:
```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "youremail@gmail.com",
    "sender_password": "abcd efgh ijkl mnop",
    "recipient_email": "youremail@gmail.com"
  }
}
```

#### Step 3: Run!
```bash
python cp2k_job_runner_final.py my_15_jobs.csv --notify-config notification_config.json --output results.csv
```

That's it! You'll get a beautiful HTML email for each job completion.

---

## What the HTML Email Looks Like

### Email Preview (Success)

```
From: youremail@gmail.com
To: youremail@gmail.com
Subject: ✅ CP2K Job Completed: protein_simulation_01

[Beautiful formatted email with:]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ protein_simulation_01
Completed Successfully
━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Job Information
├─ Job Name: protein_simulation_01
├─ Input File: /path/to/simulation.inp
├─ Output File: /path/to/simulation.out
├─ OpenMP Threads: 16
├─ Status: SUCCESS ✓
└─ Return Code: 0

⏱️ Timing
├─ Elapsed Time: 18.4567 hours (66443.41 seconds)
├─ Wall Time Limit: 24 hours
├─ Completed At: 2024-02-13 14:30:15
└─ CP2K Internal Wall Time: 66420.33 seconds

⚛️ Energy & Convergence
┌──────────────────────────┐
│   Total Energy           │
│ -1245.67891234 Ha        │
└──────────────────────────┘

├─ SCF Converged: Yes ✓
├─ SCF Steps: 45
└─ Total Force: 1.2345e-06

━━━━━━━━━━━━━━━━━━━━━━━━━━━
CP2K Job Runner
Notification sent at 2024-02-13 14:30:20
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The actual email is in **full color with gradients, boxes, and tables**!

### Email Preview (Timeout)

```
Subject: ⏰ CP2K Job Timed Out: long_md_simulation

[Orange/yellow theme with warning]
⏰ long_md_simulation
Timed Out
━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Job Information
├─ Status: TIMEOUT ⚠️
└─ Elapsed Time: 24.0000 hours (86400 seconds)

⚠️ Error Information
╔════════════════════════════════════╗
║ Job exceeded wall time limit of   ║
║ 24 hours                           ║
╚════════════════════════════════════╝
```

---

## Microsoft Teams Setup (3 Minutes)

### Step 1: Create Incoming Webhook

1. Open Microsoft Teams
2. Go to your channel (e.g., "Computational Chemistry")
3. Click **⋯** (More options) → **Connectors**
4. Find **Incoming Webhook** → **Configure**
5. Name it "CP2K Job Runner"
6. **Copy the webhook URL**

### Step 2: Add to Config

Edit `notification_config.json`:
```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "youremail@gmail.com",
    "sender_password": "your_app_password",
    "recipient_email": "youremail@gmail.com"
  },
  "teams": {
    "enabled": true,
    "webhook_url": "https://outlook.office.com/webhook/YOUR_WEBHOOK_URL_HERE"
  }
}
```

### Step 3: Test

Run your jobs - you'll get notifications in both **email AND Teams**!

### What Teams Notifications Look Like

```
╔════════════════════════════════════╗
║ CP2K Job Runner        BOT         ║
╠════════════════════════════════════╣
║ ✅ Job Completed: water_opt        ║
║                                    ║
║ Job Details                        ║
║ Status          SUCCESS            ║
║ Elapsed Time    2.3456 hours       ║
║ Wall Time Limit 4 hours            ║
║ Input File      /path/to/water.inp ║
║ OpenMP Threads  8                  ║
║                                    ║
║ Results                            ║
║ Total Energy    -17.23456789 Ha    ║
║ SCF Converged   Yes ✓              ║
║ SCF Steps       12                 ║
╚════════════════════════════════════╝
```

---

## LINE Work Setup (3 Minutes)

### Step 1: Create Bot (Admin Required)

1. Go to **LINE Work Admin** (https://works.line.biz/admin)
2. Navigate to **Bots** → **Create Bot**
3. Name: "CP2K Job Runner"
4. Select the team/group to send notifications to
5. **Copy the webhook URL**

### Step 2: Add to Config

Edit `notification_config.json`:
```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "youremail@gmail.com",
    "sender_password": "your_app_password",
    "recipient_email": "youremail@gmail.com"
  },
  "linework": {
    "enabled": true,
    "webhook_url": "https://works-webhook.linecorp.com/YOUR_WEBHOOK_URL_HERE"
  }
}
```

### What LINE Work Notifications Look Like

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
CP2K Job Runner Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Job SUCCESS: protein_sim_05

📋 Details:
• Elapsed Time: 18.4567 hours
• Wall Time Limit: 24 hours
• Input: /path/to/protein.inp
• Threads: 16

⚛️ Results:
• Energy: -1245.67891234 Ha
• SCF Converged: Yes ✓
• SCF Steps: 45

🕐 Completed: 2024-02-13 14:30:15
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Use All Three Together!

You can enable email, Teams, AND LINE Work simultaneously:

```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "youremail@gmail.com",
    "sender_password": "your_app_password",
    "recipient_email": "youremail@gmail.com"
  },
  "teams": {
    "enabled": true,
    "webhook_url": "https://outlook.office.com/webhook/..."
  },
  "linework": {
    "enabled": true,
    "webhook_url": "https://works-webhook.linecorp.com/..."
  }
}
```

**Result:**
- Personal record → Email (beautiful HTML)
- Team awareness → Teams (instant desktop notification)
- Mobile alerts → LINE Work (phone notification)

---

## Example Timeline for Your 15 Jobs

With 15 jobs at 8-24 hours each, here's what you'll receive:

```
Day 1, 10:00 AM  - Start job queue
Day 1, 6:30 PM   - 📧 Email: Job 1 complete (8.5 hours)
Day 2, 2:45 AM   - 📧 Email: Job 2 complete (8.25 hours)
Day 2, 11:15 AM  - 📧 Email: Job 3 complete (8.5 hours)
Day 2, 8:00 PM   - 📧 Email: Job 4 complete (8.75 hours)
Day 3, 6:30 AM   - 📧 Email: Job 5 complete (10.5 hours)
...
Day 8, 2:00 PM   - 📧 Email: Job 15 complete (20 hours)
Day 8, 2:01 PM   - 📧 Email: 🏁 Queue complete! 15 jobs done
```

**Total notifications: 16 emails** (15 jobs + 1 summary)
**Spread over ~8 days** (no spam!)

---

## HTML Email Features

### Color-Coded Status
- ✅ **Green** for SUCCESS
- ⏰ **Yellow/Orange** for TIMEOUT  
- ❌ **Red** for FAILED
- ⚠️ **Gray** for ERROR

### Highlighted Energy
Large, prominent display of final energy in a colored gradient box

### Complete Metrics
- Timing (elapsed vs limit)
- Energy & convergence
- SCF steps
- Forces
- Error messages (if any)

### Mobile-Friendly
Renders beautifully on:
- Gmail app (iOS/Android)
- Outlook app
- Apple Mail
- Web browsers

---

## Tips for Long-Running Jobs

### 1. Set Conservative Wall Times
For 8-24 hour jobs, set wall time to 26-30 hours:
```csv
job_file,num_cores,wall_time_hours
simulation_01.inp,16,30
simulation_02.inp,16,30
```

### 2. Monitor Email on Phone
- Enable Gmail notifications
- VIP/Priority sender for your email
- You'll wake up to completed jobs!

### 3. Use Teams for Team Awareness
If you're collaborating, Teams notifications let everyone see progress

### 4. Check Results CSV Anytime
Results are saved incrementally:
```bash
# View latest results
tail -5 cp2k_results.csv

# Count completed
grep "SUCCESS" cp2k_results.csv | wc -l
```

---

## Notification Settings Summary

### What You Get Notified About:
✅ Each job completion (SUCCESS/TIMEOUT/FAILED)
✅ Final queue summary when all 15 jobs done

### What You DON'T Get:
❌ Job start notifications (would be 15 extra emails)
❌ Progress updates every 30 min (would be 100s of emails!)
❌ Spam

### Perfect for:
- Long-running overnight/multi-day jobs
- Queues of many jobs
- When you want comprehensive results without spam

---

## Troubleshooting

### Email Not Arriving
1. Check spam/junk folder
2. Verify app password (not regular password)
3. Test with simple Python:
```python
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Test")
msg['Subject'] = "Test"
msg['From'] = "youremail@gmail.com"
msg['To'] = "youremail@gmail.com"

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login("youremail@gmail.com", "your_app_password")
    s.send_message(msg)
```

### Teams Webhook Not Working
1. Verify webhook URL is complete
2. Make sure connector wasn't deleted
3. Test with curl:
```bash
curl -H "Content-Type: application/json" -d '{
  "@type": "MessageCard",
  "title": "Test",
  "text": "Test notification"
}' YOUR_WEBHOOK_URL
```

### LINE Work Webhook Issues
1. Verify admin has enabled the bot
2. Check webhook URL format
3. Ensure bot has permission to post in the channel

### HTML Email Looks Plain
- Some email clients disable HTML by default
- Check "Display images" / "Load HTML" settings
- Gmail, Outlook, Apple Mail all support full HTML

---

## Environment Variables Alternative

Instead of config file, use environment variables:

```bash
# Email
export NOTIFY_EMAIL_ENABLED=true
export NOTIFY_SMTP_SERVER=smtp.gmail.com
export NOTIFY_SMTP_PORT=587
export NOTIFY_SENDER_EMAIL=youremail@gmail.com
export NOTIFY_SENDER_PASSWORD="your_app_password"
export NOTIFY_RECIPIENT_EMAIL=youremail@gmail.com

# Teams
export NOTIFY_TEAMS_ENABLED=true
export NOTIFY_TEAMS_WEBHOOK="https://outlook.office.com/webhook/..."

# LINE Work
export NOTIFY_LINEWORK_ENABLED=true
export NOTIFY_LINEWORK_WEBHOOK="https://works-webhook.linecorp.com/..."

# Run without config file
python cp2k_job_runner_notify_v2.py my_jobs.csv
```

---

## Complete Example

### Your Setup:
- 15 jobs
- 8-24 hours each
- Want email notifications with full results
- No spam

### Your Config (`notification_config.json`):
```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "youremail@gmail.com",
    "sender_password": "your_app_password",
    "recipient_email": "youremail@gmail.com"
  },
  "teams": {
    "enabled": false
  },
  "linework": {
    "enabled": false
  }
}
```

### Your Jobs CSV (`protein_sims.csv`):
```csv
job_name,job_file,num_cores,wall_time_hours
protein_01,/data/sims/protein_01.inp,16,24
protein_02,/data/sims/protein_02.inp,16,24
protein_03,/data/sims/protein_03.inp,16,24
protein_04,/data/sims/protein_04.inp,16,24
protein_05,/data/sims/protein_05.inp,16,24
protein_06,/data/sims/protein_06.inp,16,24
protein_07,/data/sims/protein_07.inp,16,24
protein_08,/data/sims/protein_08.inp,16,24
protein_09,/data/sims/protein_09.inp,16,24
protein_10,/data/sims/protein_10.inp,16,24
protein_11,/data/sims/protein_11.inp,16,24
protein_12,/data/sims/protein_12.inp,16,24
protein_13,/data/sims/protein_13.inp,16,24
protein_14,/data/sims/protein_14.inp,16,24
protein_15,/data/sims/protein_15.inp,16,24
```

### Run Command:
```bash
python cp2k_job_runner_notify_v2.py protein_sims.csv --notify-config notification_config.json --walltime 24
```

### What Happens:
1. Jobs run sequentially (1 at a time)
2. Each job gets 24 hours max
3. When job finishes → Beautiful HTML email sent
4. After all 15 → Summary email sent
5. Results saved to `cp2k_results.csv` after each job

### Expected Runtime:
- Average 12-16 hours per job
- Total: ~7-10 days for all 15 jobs
- You get **16 total emails** (15 completions + 1 summary)

Perfect for running while you sleep, work on other things, or go on vacation!

---

## Next Steps

1. **Create config file:**
   ```bash
   python cp2k_job_runner_notify_v2.py --create-notify-config
   ```

2. **Edit with your credentials:**
   - Gmail app password
   - Teams webhook (optional)
   - LINE Work webhook (optional)

3. **Test with one job:**
   ```bash
   # Create test CSV with just 1 job
   echo "job_file,num_cores,wall_time_hours
   test.inp,4,0.1" > test.csv
   
   # Run
   python cp2k_job_runner_notify_v2.py test.csv --notify-config notification_config.json
   ```

4. **Run your full queue:**
   ```bash
   python cp2k_job_runner_notify_v2.py my_15_jobs.csv --notify-config notification_config.json
   ```

5. **Check your email** - you'll get beautiful notifications!

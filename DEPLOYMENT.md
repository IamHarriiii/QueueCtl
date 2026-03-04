# Queuectl - Cross-Platform Deployment Guide

## Overview

Queuectl is a **cross-platform** Python application that works on any operating system with Python 3.8+. This guide covers deployment on all major platforms.

---

## Supported Operating Systems

✅ **Linux** (Ubuntu, Debian, RHEL, CentOS, Fedora, Arch, etc.)  
✅ **macOS** (10.14+, Intel & Apple Silicon)  
✅ **Windows** (10, 11, Server 2016+)  
✅ **BSD** (FreeBSD, OpenBSD)  
✅ **Unix** (Solaris, AIX)  
✅ **Container Platforms** (Docker, Kubernetes, Podman)  
✅ **Cloud Platforms** (AWS, GCP, Azure, DigitalOcean, etc.)

---

## Installation Methods

### Method 1: Direct Installation (All Platforms)

```bash
# Clone repository
git clone https://github.com/IamHarriiii/Queuectl.git
cd Queuectl

# Install dependencies
pip install -r requirements.txt

# Install queuectl
pip install -e .

# Verify installation
queuectl --help
```

### Method 2: System Package (Linux)

#### Ubuntu/Debian
```bash
# Create .deb package
sudo apt-get install python3-stdeb dh-python
python3 setup.py --command-packages=stdeb.command bdist_deb

# Install
sudo dpkg -i deb_dist/queuectl_*.deb
```

#### RHEL/CentOS/Fedora
```bash
# Create .rpm package
python3 setup.py bdist_rpm

# Install
sudo rpm -i dist/queuectl-*.rpm
```

### Method 3: Docker (All Platforms)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install queuectl
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install -e .

# Create data directory
RUN mkdir -p /data/.queuectl

# Set environment
ENV HOME=/data

EXPOSE 5000

# Default command
CMD ["queuectl", "worker", "start", "--count", "2"]
```

Build and run:

```bash
# Build image
docker build -t queuectl:latest .

# Run worker
docker run -d --name queuectl-worker \
  -v queuectl-data:/data/.queuectl \
  queuectl:latest

# Run dashboard
docker run -d --name queuectl-dashboard \
  -p 5000:5000 \
  -v queuectl-data:/data/.queuectl \
  queuectl:latest python -m queuectl.web.app
```

### Method 4: Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  queuectl-worker:
    build: .
    command: queuectl worker start --count 3
    volumes:
      - queuectl-data:/data/.queuectl
    restart: unless-stopped
    environment:
      - PYTHONUNBUFFERED=1

  queuectl-dashboard:
    build: .
    command: python -m queuectl.web.app
    ports:
      - "5000:5000"
    volumes:
      - queuectl-data:/data/.queuectl
    restart: unless-stopped
    depends_on:
      - queuectl-worker

volumes:
  queuectl-data:
```

Run:
```bash
docker-compose up -d
```

---

## Platform-Specific Setup

### Linux (systemd)

Create `/etc/systemd/system/queuectl-worker.service`:

```ini
[Unit]
Description=Queuectl Worker Service
After=network.target

[Service]
Type=simple
User=queuectl
Group=queuectl
WorkingDirectory=/opt/queuectl
ExecStart=/usr/local/bin/queuectl worker start --count 3
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable queuectl-worker
sudo systemctl start queuectl-worker
sudo systemctl status queuectl-worker
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.queuectl.worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.queuectl.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/queuectl</string>
        <string>worker</string>
        <string>start</string>
        <string>--count</string>
        <string>3</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/queuectl-worker.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/queuectl-worker.err</string>
</dict>
</plist>
```

Load service:

```bash
launchctl load ~/Library/LaunchAgents/com.queuectl.worker.plist
launchctl start com.queuectl.worker
```

### Windows (Task Scheduler)

**Option 1: Windows Service (using NSSM)**

```powershell
# Download NSSM (Non-Sucking Service Manager)
# https://nssm.cc/download

# Install service
nssm install QueuectlWorker "C:\Python311\Scripts\queuectl.exe" "worker start --count 3"

# Configure service
nssm set QueuectlWorker AppDirectory "C:\queuectl"
nssm set QueuectlWorker DisplayName "Queuectl Worker"
nssm set QueuectlWorker Description "Queuectl background job worker"
nssm set QueuectlWorker Start SERVICE_AUTO_START

# Start service
nssm start QueuectlWorker
```

**Option 2: Task Scheduler**

```powershell
# Create scheduled task
$action = New-ScheduledTaskAction -Execute "queuectl" -Argument "worker start --count 3"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3

Register-ScheduledTask -TaskName "QueuectlWorker" -Action $action -Trigger $trigger -Principal $principal -Settings $settings
```

---

## Cloud Platform Deployment

### AWS (EC2)

```bash
# Launch EC2 instance (Amazon Linux 2 or Ubuntu)
# SSH into instance

# Install Python 3.8+
sudo yum install python3 -y  # Amazon Linux
# or
sudo apt-get install python3 python3-pip -y  # Ubuntu

# Install queuectl
git clone https://github.com/IamHarriiii/Queuectl.git
cd Queuectl
pip3 install -r requirements.txt
pip3 install -e .

# Setup systemd service (see Linux section above)

# Configure security group to allow port 5000 for dashboard
```

### AWS (ECS/Fargate)

Create `task-definition.json`:

```json
{
  "family": "queuectl",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "queuectl-worker",
      "image": "your-ecr-repo/queuectl:latest",
      "command": ["queuectl", "worker", "start", "--count", "2"],
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/queuectl",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "worker"
        }
      }
    }
  ]
}
```

### Google Cloud Platform (GCE)

```bash
# Create VM instance
gcloud compute instances create queuectl-worker \
  --image-family=ubuntu-2004-lts \
  --image-project=ubuntu-os-cloud \
  --machine-type=e2-medium \
  --zone=us-central1-a

# SSH and install
gcloud compute ssh queuectl-worker --zone=us-central1-a

# Follow Linux installation steps
```

### Azure (VM)

```bash
# Create VM
az vm create \
  --resource-group myResourceGroup \
  --name queuectl-vm \
  --image UbuntuLTS \
  --admin-username azureuser \
  --generate-ssh-keys

# SSH and install
az vm ssh --resource-group myResourceGroup --name queuectl-vm

# Follow Linux installation steps
```

### Kubernetes

Create `k8s-deployment.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: queuectl-data
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: queuectl-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: queuectl-worker
  template:
    metadata:
      labels:
        app: queuectl-worker
    spec:
      containers:
      - name: worker
        image: queuectl:latest
        command: ["queuectl", "worker", "start", "--count", "2"]
        volumeMounts:
        - name: data
          mountPath: /data/.queuectl
        env:
        - name: HOME
          value: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: queuectl-data
---
apiVersion: v1
kind: Service
metadata:
  name: queuectl-dashboard
spec:
  selector:
    app: queuectl-dashboard
  ports:
  - port: 5000
    targetPort: 5000
  type: LoadBalancer
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: queuectl-dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: queuectl-dashboard
  template:
    metadata:
      labels:
        app: queuectl-dashboard
    spec:
      containers:
      - name: dashboard
        image: queuectl:latest
        command: ["python", "-m", "queuectl.web.app"]
        ports:
        - containerPort: 5000
        volumeMounts:
        - name: data
          mountPath: /data/.queuectl
        env:
        - name: HOME
          value: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: queuectl-data
```

Deploy:
```bash
kubectl apply -f k8s-deployment.yaml
```

---

## Integration with Existing Systems

### 1. Cron Jobs (Linux/macOS)

Replace cron with queuectl for better monitoring:

```bash
# Old cron job
# 0 2 * * * /path/to/backup.sh

# New queuectl approach
# Add to crontab:
0 2 * * * queuectl enqueue --command "/path/to/backup.sh" --priority high --timeout 3600
```

### 2. Windows Task Scheduler

```powershell
# Instead of direct task execution, enqueue to queuectl
queuectl enqueue --command "C:\Scripts\backup.bat" --priority high
```

### 3. CI/CD Pipelines

**GitHub Actions:**
```yaml
- name: Run background job
  run: |
    queuectl enqueue --command "python deploy.py" --priority high --timeout 1800
```

**Jenkins:**
```groovy
stage('Deploy') {
    steps {
        sh 'queuectl enqueue --command "bash deploy.sh" --priority high'
    }
}
```

### 4. Application Integration (Python)

```python
from queuectl.queue import Queue
from queuectl.storage import Storage
from queuectl.config import Config

# Initialize
storage = Storage()
config = Config(storage)
queue = Queue(storage, config)

# Enqueue job from your application
job = queue.enqueue({
    'command': 'python process_data.py --file data.csv',
    'priority': 2,  # High priority
    'timeout': 3600,
    'max_retries': 3
})

print(f"Job enqueued: {job.id}")
```

### 5. REST API Integration

Start the web dashboard and use HTTP API:

```bash
# Start dashboard
queuectl dashboard start

# Enqueue via HTTP (requires API implementation)
curl -X POST http://localhost:5000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"command":"echo hello","priority":1}'
```

---

## Production Best Practices

### 1. Database Location

**Linux/macOS:**
```bash
export QUEUECTL_DB_PATH=/var/lib/queuectl/queuectl.db
```

**Windows:**
```powershell
$env:QUEUECTL_DB_PATH = "C:\ProgramData\queuectl\queuectl.db"
```

### 2. Logging

Configure logging in production:

```python
# In your startup script
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/queuectl/worker.log'),
        logging.StreamHandler()
    ]
)
```

### 3. Monitoring

Use webhooks for monitoring:

```bash
# Add webhook for failures
queuectl webhook add \
  --url https://monitoring.example.com/alerts \
  --events "job.failed,job.timeout"
```

### 4. High Availability

Run multiple workers across multiple machines:

```bash
# Machine 1
queuectl worker start --count 4

# Machine 2
queuectl worker start --count 4

# Both share the same database (use network storage or database)
```

### 5. Backup

```bash
# Backup database
cp ~/.queuectl/queuectl.db ~/backups/queuectl-$(date +%Y%m%d).db

# Or use automated backup job
queuectl enqueue --command "backup-queuectl.sh" --priority low
```

---

## Troubleshooting

### Permission Issues (Linux)

```bash
# Create queuectl user
sudo useradd -r -s /bin/false queuectl

# Set permissions
sudo chown -R queuectl:queuectl /opt/queuectl
sudo chmod 755 /opt/queuectl
```

### Port Conflicts (Dashboard)

```bash
# Change dashboard port
python -m queuectl.web.app --port 8080
```

### Database Locked

```bash
# Check for stale connections
lsof ~/.queuectl/queuectl.db

# Kill stale processes if needed
```

---

## Summary

Queuectl works on **any platform** with Python 3.8+:

✅ **Native Installation** - Works on all OS  
✅ **Containerized** - Docker/Kubernetes  
✅ **Cloud-Ready** - AWS, GCP, Azure  
✅ **Service Integration** - systemd, launchd, Windows Service  
✅ **Cross-Platform** - Linux, macOS, Windows, BSD, Unix

Choose the deployment method that best fits your infrastructure!

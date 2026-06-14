# Phishing Data Generator

A security research service that generates phishing page variants across **25 documented evasion techniques** for building anti-phishing ML training datasets and testing detection systems.

> **For authorized security research, anti-phishing dataset generation, and detection system testing only.**

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| **UI** | `3050` | Web interface - upload HTML, analyze, generate |
| **API** | `8000` | FastAPI backend - REST endpoints + Swagger docs |

---

## Prerequisites

Install these on your server before proceeding:

```bash
# Docker Engine (20.10+)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Docker Compose plugin (v2)
sudo apt-get install -y docker-compose-plugin   # Debian/Ubuntu
# or
docker compose version    # verify it's available
```

Verify:

```bash
docker --version          # Docker version 24.x or higher
docker compose version    # Docker Compose version v2.x
```

---

## Step-by-Step: Running on a Server

### Step 1 - Clone the repository

```bash
git clone https://github.com/your-org/phish_data_generator.git
cd phish_data_generator
```

### Step 2 - Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```bash
nano .env
```

```env
# Required for Technique 23 (AI full-page cloning via Claude API)
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional - for Technique 8 (Clearbit favicon loading)
CLEARBIT_API_KEY=
```

> If you skip `ANTHROPIC_API_KEY`, Technique 23 will report itself as skipped but all other 24 techniques work without it.

### Step 3 - Build and start

```bash
docker compose up --build -d
```

What this does:
- Builds the **FastAPI backend** image from `Dockerfile`
- Builds the **nginx UI** image from `ui/Dockerfile`
- Starts both containers in the background
- The backend must pass its health check before the UI starts

Expected output:

```
[+] Building ...
 ✔ backend  Built
 ✔ ui       Built
[+] Running 2/2
 ✔ Container phishgen_api  Started
 ✔ Container phishgen_ui   Started
```

### Step 4 - Verify services are running

```bash
# Check both containers are healthy
docker compose ps

# Expected output:
# NAME            STATUS              PORTS
# phishgen_api    Up (healthy)        0.0.0.0:8000->8000/tcp
# phishgen_ui     Up                  0.0.0.0:3050->80/tcp
```

Test the API directly:

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/techniques | python3 -m json.tool | head -20
# 25 techniques listed
```

### Step 5 - Access the interfaces

| Interface | URL |
|-----------|-----|
| Web UI | `http://YOUR_SERVER_IP:3050` |
| Swagger (interactive API docs) | `http://YOUR_SERVER_IP:8000/docs` |
| ReDoc (API reference) | `http://YOUR_SERVER_IP:8000/redoc` |

Replace `YOUR_SERVER_IP` with your server's IP address or hostname.

---

## UI Usage Guide

### 1. Enter target information (left panel)

- **Target URL** - the URL of the website you are generating phishing variants for
  (e.g. `https://www.microsoft.com/en-us/login`)
- **HTML File** - upload the saved HTML source of that page
  (right-click → Save As in browser, or use `wget`/`curl`)
- **Screenshot** - optional reference image for AI cloning (Technique 23)

Click **Analyze Target**.

### 2. Review applicability (right panel - Step 2)

The analyzer checks your HTML for:

| Feature | Affects |
|---------|---------|
| `<input>` / `<form>` tags | Shadow DOM (T11), MFA fatigue (T21), Baseline (T25) |
| `<img>` / `<svg>` tags | Logo edit (T7), Favicon (T8), SVG smuggling (T9), Stego (T24) |
| Any HTML content | All HTML/DOM/JS evasion techniques (T10-T16) |

- **Green cards** = applicable - checkbox enabled, click ⚙ to expand options
- **Dimmed cards** = not applicable - reason shown inline (e.g. "Requires `<form>` elements")
- Use **Select all applicable** to pick every usable technique at once

### 3. Set generation options (left panel - Step 3)

| Option | Description |
|--------|-------------|
| **Hybrid Mode** ON | Techniques chain sequentially - each gets the previous technique's output HTML/URL |
| **Hybrid Mode** OFF | Each technique applied independently to the original HTML/URL |
| **Include Report** | Adds `report.md` to the ZIP with a full Markdown change log |

Click **Generate Phishing Variants**.

### 4. Download output (right panel - Step 4)

The ZIP archive contains:

```
phish_<run_id>.zip
├── modified.html              ← final phishing HTML (all techniques applied)
├── report.md                  ← change-by-change Markdown report
├── url_variations.txt         ← all mutated URLs from URL-manipulation techniques
├── evilginx_phishlet.yaml     ← (T20) Evilginx2 reverse-proxy config
├── nginx_proxy_snippet.conf   ← (T20) nginx proxy config snippet
├── qr_code.png                ← (T18) PNG QR code pointing to phishing URL
├── qr_ascii.txt               ← (T18) ASCII QR code for emails/PDFs
├── redirect_chain.html        ← (T6)  multi-hop redirect entry page
├── redirect_chain.txt         ← (T6)  redirect chain URL map
├── punycode_info.txt          ← (T2)  punycode domain details
├── url_polymorphic_variants.txt ← (T5) N polymorphic URL variants
├── captcha_stage1.html        ← (T17) fake CAPTCHA gate page
├── credential_stage2.html     ← (T17) credential form page
├── oauth_consent_page.html    ← (T22) fake OAuth consent page
└── images/
    ├── modified_logo_0.png    ← (T7)  pixel-edited logo
    ├── modified_favicon.png   ← (T8)  modified favicon
    └── stego_carrier.png      ← (T24) steganography carrier image
```

---

## API Usage (direct / programmatic)

### List all 25 techniques

```bash
curl http://localhost:8000/techniques
```

### Analyze HTML applicability

```bash
curl -X POST http://localhost:8000/analyze \
  -F "url=https://www.example.com/login" \
  -F "html_file=@/path/to/page.html"
```

Response:

```json
{
  "url": "https://www.example.com/login",
  "html_features": { "has_input_fields": true, "has_images": true, ... },
  "applicable": [ { "technique_id": 1, "technique_name": "Homoglyph / Confusable Characters", ... } ],
  "inapplicable": [ { "technique_id": 11, "reason": "Not applicable - Requires <form> elements", ... } ],
  "applicable_count": 22,
  "inapplicable_count": 3
}
```

### Generate phishing variants

```bash
curl -X POST http://localhost:8000/generate \
  -F "url=https://www.example.com/login" \
  -F "html_file=@/path/to/page.html" \
  -F 'technique_configs=[{"technique_id":1},{"technique_id":4},{"technique_id":10}]' \
  -F "hybrid_mode=true" \
  -F "include_report=true" \
  --output phish_output.zip
```

---

## Technique Reference

| ID | Name | Group | Requires |
|----|------|-------|----------|
| 1 | Homoglyph / Confusable Characters | URL Manipulation | URL |
| 2 | Punycode / IDN Homograph | URL Manipulation | URL |
| 3 | Look-alike + Leetspeak + Trust Words | URL Manipulation | URL |
| 4 | Long URL + Random Hash Parameters | URL Manipulation | URL |
| 5 | Polymorphic URL Variations | URL Manipulation | URL |
| 6 | Multi-stage Redirect Chain | URL Manipulation | URL |
| 7 | Logo Pixel-Level Editing | Visual Mimicry | Images in HTML |
| 8 | Favicon Mimicry | Visual Mimicry | Images in HTML |
| 9 | SVG Smuggling (Embedded JS) | Visual Mimicry | Images in HTML |
| 10 | Dynamic DOM Generation via JS | HTML/DOM/JS | HTML |
| 11 | Shadow DOM Encapsulation | HTML/DOM/JS | Form fields |
| 12 | CSS Hiding (Off-Viewport) | HTML/DOM/JS | HTML |
| 13 | Anti-bot Fingerprinting | HTML/DOM/JS | HTML |
| 14 | Hidden iframes / GhostFrame | HTML/DOM/JS | HTML |
| 15 | Geo/UA Fencing & Cloaking | Anti-bot | HTML |
| 16 | Fake CAPTCHA Overlay | Anti-bot | HTML |
| 17 | Multi-stage Captcha Flow | Delivery | Always |
| 18 | QR Code / Quishing | Delivery | Always |
| 19 | Blob URI Dynamic QR | Delivery | Always |
| 20 | AiTM Proxy Config (Evilginx) | MFA Bypass | Always |
| 21 | MFA Fatigue Simulation | MFA Bypass | Form fields |
| 22 | OAuth Consent Phishing | MFA Bypass | Always |
| 23 | AI Full-Page Cloning (Claude API) | Advanced/AI | HTML + API key |
| 24 | LSB Steganography in Images | Advanced/AI | Images in HTML |
| 25 | Baseline Phishing Form | Advanced/AI | HTML |

---

## Verifying a healthy install

After deploying, confirm the platform crawls real sites and runs every
technique end-to-end:

```bash
docker compose exec backend python -m app.smoketest
```

This crawls a small curated set of URLs from `tests/data/smoketest_urls.csv`
(Persian + English + SPA + a deliberately-invalid host to verify
unreachable handling), then applies all 25 techniques in non-hybrid mode
against each saved page. Output is a per-URL breakdown table:

```
URL                                           CRAWL     LANG  WAIT       APPLIED   NOTE
https://example.com/                          ok        en    networkidle 25/25
https://www.bbc.com/persian                   ok        fa    networkidle 25/25
https://nonexistent-host-12345.invalid/       unreach   ?                 0/25
...
Crawl success rate:  90% (9/10)
Technique apply rate: 96% (216/225)
✅ SMOKETEST PASSED - crawl ≥60% + technique apply ≥90%
```

Exit code is 0 only if **≥ 60% of URLs crawled** and **≥ 90% of
(URL, technique) pairs applied** - gates a deployment.

Per-technique unit tests live under `tests/techniques/`:

```bash
docker compose exec backend pytest tests/techniques -v
```

See [`docs/test_methods.md`](docs/test_methods.md) for the test
methodology and what each test asserts.

### Offline per-technique verification

The smoke-test above needs network + Playwright. For a faster offline
pass that proves every technique runs on a mock Persian + English login
page (and that visible-text techniques speak the right language):

```bash
docker compose exec backend python -m app.verify_techniques --clean
```

It runs all 25 techniques against two in-memory fixtures, writes each
output under `out/verify/t{NN}_{fa|en}/` so you can open the resulting
HTML in a browser, and prints a PASS/FAIL table:

```
=== Visible-text language match ===
TID NAME                          MATCH   REASON
6   Multi-stage Redirect          PASS    fa=14 en_latin=24
16  Fake CAPTCHA Overlay…         PASS    fa=72 en_latin=180
17  Multi-stage Captcha Flow      PASS    fa=66 en_latin=164
…
Crashes:                   0
Language-match failures:   0
VERIFY PASSED
```

Exit code is non-zero on any crash or language-match failure - also
gates a deployment.

---

## Logs and Monitoring

```bash
# Follow live logs from both services
docker compose logs -f

# Backend only
docker compose logs -f backend

# UI / nginx only
docker compose logs -f ui

# Check resource usage
docker stats phishgen_api phishgen_ui
```

---

## Stopping and Restarting

```bash
# Stop without removing containers
docker compose stop

# Restart
docker compose restart

# Stop and remove containers (keeps images)
docker compose down

# Full clean: remove containers + images
docker compose down --rmi all
```

---

## Rebuilding After Code Changes

```bash
# Rebuild both images and restart
docker compose up --build -d

# Rebuild backend only (e.g., after technique changes)
docker compose build backend
docker compose up -d backend

# Rebuild UI only (e.g., after HTML/CSS changes)
docker compose build ui
docker compose up -d ui
```

---

## Firewall / Port Configuration

If your server has a firewall, open the required ports:

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 3050/tcp    # UI
sudo ufw allow 8000/tcp    # API (optional - only if direct API access needed)
sudo ufw reload

# firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=3050/tcp
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

> Tip: If you only want to expose the UI publicly and keep the API internal, omit port 8000 from firewall rules. The UI proxies all API calls through nginx on port 3050 internally.

---

## Offline / Air-Gapped Installation

Two approaches - pick the one that fits your situation.

---

### Approach A - Build on internet machine, transfer images (recommended)

This is the fastest path. Build the Docker images once on any machine with internet access, export them as a tar bundle, then load and run on the air-gapped machine.

**On the internet-connected machine:**

```bash
# 1. Clone the repo and build images
git clone https://github.com/your-org/phish_data_generator.git
cd phish_data_generator
docker compose build

# 2. Verify the image names (should show phishgen_api and phishgen_ui)
docker images | grep phishgen

# 3. Export both images to a single tar file
docker save phishgen_api:latest phishgen_ui:latest -o phishgen_images.tar

# 4. Copy the repo folder + images to a USB drive / shared storage
#    You need: phishgen_images.tar  +  the entire repo folder
#    (docker-compose.yml, .env.example, ui/, app/, etc.)
```

**Transfer** `phishgen_images.tar` and the repo folder to the air-gapped machine (USB, SCP, shared drive).

**On the air-gapped machine:**

```bash
# Prerequisites: Docker Engine + Docker Compose plugin must already be installed
# (see Approach B below if Docker itself is not installed)

# 1. Load the images
docker load -i phishgen_images.tar

# Verify they loaded
docker images | grep phishgen

# 2. Enter the repo folder and configure environment
cd phish_data_generator
cp .env.example .env
nano .env   # fill in ANTHROPIC_API_KEY if you need T23

# 3. Start (no --build needed - images are already loaded)
docker compose up -d

# 4. Verify
docker compose ps
curl http://localhost:8009/health
```

---

### Approach B - Bundle everything from scratch (Docker + Python packages + system libs)

Use this when the target machine has no Docker at all, or when you need a fully reproducible bundle.

#### Step 1 - Download Docker Engine installer (offline .deb / .rpm packages)

```bash
# On online machine - download Docker offline packages for Ubuntu/Debian
mkdir docker-offline
cd docker-offline

# Substitute your target OS version (check https://download.docker.com/linux/ubuntu/dists/)
DOCKER_VERSION=26.1.4
OS=ubuntu
CODENAME=jammy    # or focal, bookworm, etc.
ARCH=amd64

# Download the 4 required .deb packages
wget "https://download.docker.com/linux/${OS}/dists/${CODENAME}/pool/stable/${ARCH}/containerd.io_1.6.33-1_${ARCH}.deb"
wget "https://download.docker.com/linux/${OS}/dists/${CODENAME}/pool/stable/${ARCH}/docker-ce_${DOCKER_VERSION}-1~${OS}.${CODENAME}_${ARCH}.deb"
wget "https://download.docker.com/linux/${OS}/dists/${CODENAME}/pool/stable/${ARCH}/docker-ce-cli_${DOCKER_VERSION}-1~${OS}.${CODENAME}_${ARCH}.deb"
wget "https://download.docker.com/linux/${OS}/dists/${CODENAME}/pool/stable/${ARCH}/docker-compose-plugin_2.27.1-1~${OS}.${CODENAME}_${ARCH}.deb"
```

> For exact package filenames, browse `https://download.docker.com/linux/ubuntu/dists/<codename>/pool/stable/amd64/` on the online machine.

**On the air-gapped machine:**

```bash
# Install Docker from local .deb files
sudo dpkg -i containerd.io_*.deb docker-ce-cli_*.deb docker-ce_*.deb docker-compose-plugin_*.deb
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

#### Step 2 - Pull base images and save them

```bash
# On online machine
docker pull python:3.11-slim
docker pull nginx:alpine

docker save python:3.11-slim nginx:alpine -o base_images.tar
```

#### Step 3 - Download Python wheels

```bash
# On online machine (same Python version as the base image: 3.11)
pip download -r requirements.txt -d ./pip_wheels/ --python-version 3.11 --platform manylinux_2_17_x86_64 --only-binary=:all:

# If some packages don't have binary wheels, also run without --only-binary:
pip download -r requirements.txt -d ./pip_wheels/
```

#### Step 4 - Bundle and transfer

```bash
# On online machine - create a single transfer bundle
tar czf phishgen_offline_bundle.tar.gz \
    phish_data_generator/ \
    base_images.tar \
    docker-offline/ \
    pip_wheels/
```

Transfer the bundle to the air-gapped machine.

#### Step 5 - Install on air-gapped machine

```bash
# Extract the bundle
tar xzf phishgen_offline_bundle.tar.gz

# 1. Install Docker (if not already installed)
cd docker-offline
sudo dpkg -i containerd.io_*.deb docker-ce-cli_*.deb docker-ce_*.deb docker-compose-plugin_*.deb
sudo systemctl enable --now docker && sudo usermod -aG docker $USER && newgrp docker

# 2. Load base images
docker load -i base_images.tar

# 3. Patch the Dockerfiles to install Python packages from local wheels
#    Add --find-links /wheels --no-index flags:
sed -i 's|RUN pip install --no-cache-dir -r requirements.txt|COPY ../pip_wheels /wheels\nRUN pip install --no-cache-dir --find-links /wheels --no-index -r requirements.txt|' \
    phish_data_generator/Dockerfile

# 4. Build images (uses local base images + local wheels - no internet)
cd phish_data_generator
cp .env.example .env
docker compose build

# 5. Start
docker compose up -d
docker compose ps
curl http://localhost:8009/health
```

---

### Quick reference - what each file in the bundle provides

| File / folder | Purpose |
|---------------|---------|
| `phish_data_generator/` | Application source code + docker-compose.yml |
| `base_images.tar` | `python:3.11-slim` and `nginx:alpine` Docker base images |
| `docker-offline/` | Docker Engine `.deb` packages for air-gapped installation |
| `pip_wheels/` | Pre-downloaded Python package wheels (all dependencies) |

---

## Troubleshooting

### UI shows "API Offline"

```bash
# Check backend is running and healthy
docker compose ps
docker compose logs backend --tail=50

# Test backend directly
curl http://localhost:8000/health
```

### Backend fails to start

```bash
docker compose logs backend
# Common causes:
# - Port 8000 already in use: sudo lsof -i :8000
# - Missing system libs: docker compose build backend --no-cache
```

### Port 3050 already in use

```bash
sudo lsof -i :3050
# Change the port in docker-compose.yml:
# "3051:80"   ← host_port:container_port
```

### `KeyError: 'id'` in `watch_events` when starting the stack / running a crawl

```
Exception in thread Thread-3 (watch_events):
  ...
  File ".../compose/project.py", line 594, in build_container_event
    container = Container.from_id(self.client, event['id'])
KeyError: 'id'
```

**Cause:** you are using the *deprecated* **docker-compose v1** (the Python tool at
`/usr/lib/python3/dist-packages/compose/`). Newer Docker Engines emit some events
without a top-level `id` field, which crashes v1's attached event-watcher thread.
The crawler runs *inside* the `backend` container - bringing the stack up attached
and then triggering a crawl fires the events that crash the watcher. **It is a
docker-compose v1 bug, not an app bug** - the containers keep running; only the
foreground log/event watcher thread dies.

**Fix - use Docker Compose v2** (this is what the rest of this README assumes):

```bash
# Install the v2 plugin (Debian/Ubuntu)
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
docker compose version          # should print v2.x

# Then ALWAYS use the space form, not the hyphen form:
docker compose up -d            # ✅ docker compose  (v2)
# docker-compose up             # ❌ docker-compose (v1, buggy)
```

**Instant workaround if you must keep v1:** run detached so the attached watcher
thread is never started:

```bash
docker-compose up -d            # the crashing watcher only runs in attached mode
docker-compose logs -f backend  # follow logs without it
```

### Technique 23 (AI Cloning) always skipped

```bash
# Verify ANTHROPIC_API_KEY is set
docker compose exec backend env | grep ANTHROPIC
# If empty, edit .env and restart:
docker compose up -d backend
```

### Large HTML files fail to upload

The nginx proxy allows up to **20 MB** per upload. For larger files, edit `ui/nginx.conf`:

```nginx
client_max_body_size 50m;   # increase limit
```

Then rebuild the UI:

```bash
docker compose build ui && docker compose up -d ui
```

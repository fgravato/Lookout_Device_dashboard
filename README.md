# Lookout MRA Device Dashboard

Flask web application for managing mobile devices via the Lookout Mobile Risk API v2. Provides a real-time dashboard with device filtering, Excel export, CVE vulnerability scanning, multi-tenant support, and intelligent caching.

## Features

- **Device Dashboard** — Real-time device inventory with status summaries (connected, stale, disconnected)
- **Advanced Filtering** — Filter by platform, risk level, protection status, connection status, days since check-in, and more
- **Excel Export** — Export filtered device data with summary sheets via openpyxl
- **CVE Vulnerability Scanning** — Scan device fleet against known CVEs
- **Multi-Tenant Support** — Manage multiple Lookout tenants from a single dashboard
- **Intelligent Caching** — In-memory + SQLite persistence with background refresh and delta sync
- **Authentication** — Optional HTTP Basic auth with Werkzeug password hashing
- **Rate Limiting** — Built-in Flask-Limiter protection on API endpoints

## Prerequisites

- Python 3.8 or higher
- Lookout Mobile Endpoint Protection account with API access (or use sample data mode for development)

## Installation

### macOS / Linux

```bash
# Extract the zip file
unzip Lookout-Reporting_tool_version1.zip
cd Lookout-Reporting_tool_version1

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Windows

> **Python required:** Download and install Python 3.8+ from [python.org](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"**.

**Option A — Using Command Prompt:**

```cmd
:: Extract the zip file to a folder, then open Command Prompt and navigate to it
cd C:\Users\YourName\Downloads\Lookout-Reporting_tool_version1

:: Create a virtual environment
python -m venv venv

:: Activate the virtual environment
venv\Scripts\activate.bat

:: Install dependencies
pip install -r requirements.txt
```

**Option B — Using PowerShell:**

```powershell
# Extract the zip file to a folder, then open PowerShell and navigate to it
cd C:\Users\YourName\Downloads\Lookout-Reporting_tool_version1

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# NOTE: If you get an execution policy error, run this first:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

**Verify installation:**

```cmd
python -c "import flask; print('Flask', flask.__version__)"
```

If you see `Flask 3.0.0`, the installation was successful.

### Dependencies

| Package | Purpose |
|---------|---------|
| Flask 3.0 | Web framework |
| requests 2.31 | HTTP client for Lookout API |
| openpyxl 3.1 | Excel file generation |
| python-dotenv 1.0 | Environment variable management |
| Flask-HTTPAuth 4.8 | HTTP Basic authentication |
| Flask-Limiter 3.5 | API rate limiting |
| python-dateutil 2.8 | Date/time utilities |

## Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env          # macOS/Linux
copy .env.example .env        # Windows
```

Open `.env` in any text editor and update the values for your environment.

### Required Settings

| Variable | Description |
|----------|-------------|
| `LOOKOUT_APPLICATION_KEY` | Your Lookout API application key (not needed if using sample data) |

### Common Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_SAMPLE_DATA` | `false` | Use built-in sample data instead of real API |
| `AUTH_ENABLED` | `false` | Enable HTTP Basic authentication |
| `AUTH_USERS` | — | User credentials in format `user:pass,user2:pass2` |
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `5000` | Server port |
| `DEBUG` | `false` | Enable Flask debug mode |
| `FLASK_ENV` | `default` | Environment: `development`, `production`, or `testing` |
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |

### Cache Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_ENABLED` | `true` | Enable in-memory caching |
| `CACHE_MAX_AGE_MINUTES` | `60` | Cache TTL in minutes |
| `ENABLE_DISK_CACHE` | `true` | Persist cache to SQLite (survives restarts) |
| `CACHE_FILE_PATH` | `./device_cache.db` | SQLite cache file location |
| `AUTO_REFRESH_ON_STARTUP` | `true` | Fetch device data on app startup |
| `BACKGROUND_REFRESH_ENABLED` | `false` | Enable background cache refresh thread |
| `BACKGROUND_REFRESH_INTERVAL_MINUTES` | `30` | Background refresh interval |
| `ENABLE_DELTA_SYNC` | `true` | Fetch only changed devices on refresh |
| `DELTA_SYNC_LOOKBACK_HOURS` | `24` | Delta sync time window |

### Multi-Tenant Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_MULTI_TENANT` | `false` | Enable multi-tenant mode |
| `TENANTS_CONFIG_FILE` | `./tenants.json` | Path to tenant configuration file |

### API Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `API_TIMEOUT` | `30` | API request timeout in seconds |
| `API_RETRY_ATTEMPTS` | `3` | Number of retry attempts on failure |
| `MAX_DEVICES_PER_REQUEST` | `1000` | Devices per API page (max 1000) |

### Getting Your Lookout Application Key

1. Log into the [Lookout Console](https://app.lookout.com) as an administrator
2. Navigate to **System > Application Keys**
3. Click **GENERATE KEY** and enter a label
4. Copy the generated key immediately (it cannot be retrieved later)
5. Add it to your `.env` file

## Running the Application

### Development (Sample Data)

No API key required.

**macOS / Linux:**
```bash
USE_SAMPLE_DATA=true python app.py
```

**Windows (Command Prompt):**
```cmd
set USE_SAMPLE_DATA=true
python app.py
```

**Windows (PowerShell):**
```powershell
$env:USE_SAMPLE_DATA="true"
python app.py
```

### Production

```bash
python run_dashboard.py
```

The launcher script checks dependencies and configuration, prints a status summary, and opens the browser automatically.

Alternatively, run directly:

```bash
python app.py
```

The dashboard is available at `http://localhost:5001` by default.

> **Windows firewall:** On first run, Windows may prompt you to allow Python through the firewall. Click **Allow access** to enable the local web server.

### Recommended Configuration by Fleet Size

**Small fleet (< 1,000 devices):**
```bash
CACHE_MAX_AGE_MINUTES=30
BACKGROUND_REFRESH_ENABLED=false
ENABLE_DISK_CACHE=false
```

**Medium fleet (1,000 - 10,000 devices):**
```bash
CACHE_MAX_AGE_MINUTES=60
BACKGROUND_REFRESH_ENABLED=true
BACKGROUND_REFRESH_INTERVAL_MINUTES=30
ENABLE_DISK_CACHE=true
```

**Large fleet (10,000+ devices):**
```bash
CACHE_MAX_AGE_MINUTES=120
BACKGROUND_REFRESH_ENABLED=true
BACKGROUND_REFRESH_INTERVAL_MINUTES=60
ENABLE_DISK_CACHE=true
ENABLE_DELTA_SYNC=true
```

## API Endpoints

All endpoints require authentication when `AUTH_ENABLED=true`, except `/health`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/health` | Health check (no auth required) |
| `GET` | `/api/devices` | Filtered device list with cache metadata |
| `GET` | `/api/device/<id>` | Single device with risk analysis |
| `POST` | `/api/refresh` | Trigger cache refresh |
| `GET` | `/api/export/excel` | Excel download of filtered devices |
| `GET/POST` | `/api/cve/*` | CVE vulnerability scanning endpoints |
| `GET/POST` | `/api/tenants/*` | Tenant management endpoints |
| `GET` | `/api/cache/*` | Cache status and management |

### Query Parameters for Device Filtering

```
GET /api/devices?platform=IOS&security_status=THREATS_HIGH&min_last_seen_days=7&max_last_seen_days=30
```

## Project Structure

```
Lookout-Reporting_tool_version1/
├── app.py                  # App factory (create_app), error handlers, background refresh
├── config.py               # Configuration classes (Dev/Prod/Test) from env vars
├── run_dashboard.py        # Production launcher with dependency checks
├── lookout_client.py       # LookoutMRAClient — OAuth2 API client with retry logic
├── device_cache.py         # DeviceCache — thread-safe in-memory + SQLite persistence
├── auth/
│   └── manager.py          # AuthManager — HTTP Basic auth with password hashing
├── routes/                 # Flask Blueprints
│   ├── devices.py          # Device listing and detail endpoints
│   ├── export.py           # Excel/CSV export endpoints
│   ├── cve.py              # CVE scanning endpoints
│   ├── tenants.py          # Multi-tenant management
│   └── cache.py            # Cache status and control
├── services/               # Business logic layer
│   ├── device_service.py   # Device fetching, caching, delta sync
│   ├── risk_service.py     # Per-device risk analysis
│   ├── export_service.py   # Excel/CSV generation
│   ├── cve_service.py      # CVE vulnerability scanning
│   ├── tenant_service.py   # Multi-tenant client management
│   └── export/sheets/      # Excel sheet generators
├── utils/
│   ├── device_filters.py   # Query-parameter filtering logic
│   └── time_utils.py       # Date/time helpers
├── templates/              # Jinja2 HTML templates
├── static/                 # CSS, JS, images
├── tests/
│   ├── conftest.py         # Test fixtures and TestConfig
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── requirements.txt        # Python dependencies
├── setup.cfg               # Pytest configuration
├── .env.example            # Environment variable template
├── tenants.json.example    # Multi-tenant configuration template
└── sample_data.json        # Built-in sample device data
```

## Architecture

The application uses the **Flask app factory pattern** with Blueprints for routing and service classes for business logic.

```
Request → Blueprint route (routes/) → Service class (services/) → LookoutMRAClient / DeviceCache → Response
```

Services are injected into the app via `app.extensions` and accessed in route handlers.

### Caching Strategy

Two-layer cache for performance with large device fleets:

1. **In-memory dict** — Primary cache, thread-safe via `threading.RLock`
2. **SQLite on disk** — Optional persistence layer, survives app restarts

Background refresh and delta sync minimize API calls. Delta sync fetches only devices changed within a configurable time window.

## Testing

```bash
# Run all tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Single test
pytest -k "test_name"

# With coverage
pytest --cov
```

Tests use `TestingConfig` with sample data enabled, auth disabled, and caching disabled. Services are mocked via `app.extensions`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **401 Unauthorized** from Lookout API | Verify `LOOKOUT_APPLICATION_KEY` is correct and not expired |
| **429 Too Many Requests** | Reduce refresh frequency; enable delta sync and disk cache |
| **Slow startup with large fleet** | Enable `ENABLE_DISK_CACHE=true` — subsequent starts load from SQLite in ~2 seconds |
| **Cache empty on every restart** | Ensure `ENABLE_DISK_CACHE=true` and `CACHE_FILE_PATH` is writable |
| **Port already in use** | Change `PORT` in `.env` or stop the other process |
| **Missing dependencies** | Run `pip install -r requirements.txt` |
| **`python` not recognized (Windows)** | Reinstall Python with **"Add Python to PATH"** checked, or use the full path `C:\Python3x\python.exe` |
| **PowerShell script execution error** | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` then retry |
| **`venv` folder already in zip** | Delete the existing `venv` folder and create a fresh one with `python -m venv venv` |

## License

Internal application. Modify as needed for your organization's requirements.

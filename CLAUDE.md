# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask web application (Python 3.8+) for managing mobile devices via the Lookout Mobile Risk API v2. Provides a dashboard with device filtering, Excel export, CVE vulnerability scanning, multi-tenant support, and intelligent caching.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run (production mode)
python run_dashboard.py

# Run (development with sample data, no API key needed)
USE_SAMPLE_DATA=true python app.py

# Run tests
pytest                    # all tests (verbose, short traceback via setup.cfg)
pytest tests/unit/        # unit tests only
pytest tests/integration/ # integration tests only
pytest -k "test_name"     # single test by name
pytest --cov              # with coverage report
```

The app runs on `http://localhost:5001` by default. No formal CI pipeline exists; testing is primarily manual via UI and API endpoints.

## Architecture

**App factory pattern** in `app.py` via `create_app()`. Routes use Flask Blueprints, business logic lives in service classes with dependency injection, and services are stored in `app.extensions`.

### Request flow

```
Request → Blueprint route (routes/) → Service class (services/) → LookoutMRAClient / DeviceCache → Response
```

### Key modules

| Module | Role |
|--------|------|
| `app.py` | App factory, error handlers, Flask-Limiter setup, background refresh thread |
| `config.py` | `Config` base + `DevelopmentConfig`, `ProductionConfig`, `TestingConfig`; all from env vars |
| `lookout_client.py` | `LookoutMRAClient` — OAuth2 client with automatic token refresh, retry, rate-limit handling |
| `device_cache.py` | `DeviceCache` — thread-safe (RLock) in-memory cache + optional SQLite persistence; `enhanced_device_mapping` normalizes API data |
| `auth/manager.py` | `AuthManager` — Basic HTTP auth with Werkzeug password hashing |

### Services (`services/`)

- `DeviceService` — fetch, cache, delta sync; orchestrates `LookoutMRAClient` and `DeviceCache`
- `RiskService` — per-device risk analysis and recommendations
- `ExportService` — Excel/CSV generation via openpyxl (sheet generators in `services/export/sheets/`)
- `CVEService` — vulnerability scanning against device fleet
- `TenantService` — multi-tenant client management

### Routes (`routes/`)

All require auth except `GET /health`. Key endpoints:
- `GET /api/devices` — filtered device list with cache metadata
- `GET /api/device/<id>` — single device with risk analysis
- `POST /api/refresh` — trigger cache refresh
- `GET /api/export/excel` — Excel download of filtered devices
- `/api/cve/*`, `/api/tenants/*`, `/api/cache/*`

### Utilities (`utils/`)

- `device_filters.py` — `apply_device_filters()` for query-param filtering
- `time_utils.py` — `days_since_checkin()`, `get_connection_status()`

## Caching Strategy

Two layers: in-memory dict (primary) + SQLite on disk (optional, survives restarts). Configured via `CACHE_ENABLED`, `CACHE_MAX_AGE_MINUTES`, `ENABLE_DISK_CACHE`, `CACHE_FILE_PATH`. Background refresh and delta sync reduce API calls for large fleets (10K+ devices). All cache operations are thread-safe via `threading.RLock`.

## Testing

Tests use `TestConfig` (defined in `tests/conftest.py`): sample data enabled, auth disabled, caching disabled. Key fixtures: `app`, `client`, `sample_device`, `sample_devices`, `mock_config`. Services are mocked via `app.extensions`.

## Code Conventions

- **Type hints** required on all function signatures
- **Google-style docstrings** with Args/Returns/Raises
- **Import order**: stdlib → third-party → local
- **Naming**: PascalCase classes, snake_case functions/vars, UPPER_CASE config constants, `_underscore` private methods
- **Error handling**: Custom exceptions (`LookoutAPIError`, `APIError`) + `logging.getLogger(__name__)` per module + graceful fallbacks
- **Config**: All settings from environment variables via `os.getenv()` with defaults; `.env` file loaded by python-dotenv

## Environment Modes

| Mode | How to activate | Behavior |
|------|-----------------|----------|
| Development | `FLASK_ENV=development` | Sample data, debug=true, short cache TTL |
| Production | `FLASK_ENV=production` | Real API, validation required, strict defaults |
| Testing | `create_app('testing')` | No caching, sample data, auth disabled |
| Sample Data | `USE_SAMPLE_DATA=true` | Uses built-in sample data instead of API |

## Key Environment Variables

See `.env.example` for the full list. Most critical:
- `LOOKOUT_APPLICATION_KEY` — required for real API access
- `USE_SAMPLE_DATA` — set `true` for development without API
- `AUTH_ENABLED` / `AUTH_USERS` — authentication toggle and user credentials
- `ENABLE_MULTI_TENANT` / `TENANTS_CONFIG_FILE` — multi-tenant mode
- `ENABLE_DISK_CACHE` / `BACKGROUND_REFRESH_ENABLED` / `ENABLE_DELTA_SYNC` — caching tuning

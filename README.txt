================================================================================
  LOOKOUT MRA DESKTOP DASHBOARD
  Installation & Configuration Guide
================================================================================

  Support: frank.gravato@lookout.com
  Version: 1.0
  Compatibility: Windows 11 | macOS (Monterey 12+)

================================================================================
  OVERVIEW
================================================================================

The Lookout MRA Desktop Dashboard is a locally-hosted web application that
connects to the Lookout Mobile Risk API v2 to provide:

  - Real-time device fleet visibility and risk monitoring
  - Device filtering by platform, risk level, compliance status, and more
  - CVE vulnerability scanning across your device fleet
  - Excel and CSV export of device data
  - Multi-tenant support (manage multiple Lookout accounts)
  - Intelligent caching for large fleets (10,000+ devices)

The dashboard runs entirely on your local machine. No data is sent to any
third-party service other than the Lookout API.

================================================================================
  REQUIREMENTS
================================================================================

  - Python 3.8 or later  (3.10+ recommended)
  - Internet access to reach the Lookout MRA API
  - A valid Lookout Application Key (obtain from your Lookout admin console)

================================================================================
  SECTION 1 — INSTALLATION ON MACOS
================================================================================

Step 1: Verify Python is installed
------------------------------------
  Open Terminal (Applications > Utilities > Terminal) and run:

      python3 --version

  You should see Python 3.8 or later. If not, download Python from:
      https://www.python.org/downloads/

Step 2: Extract the package
------------------------------------
  Double-click the ZIP file to extract it, or in Terminal run:

      cd ~/Downloads
      unzip lookout-mra-dashboard.zip
      cd lookout-mra-dashboard

Step 3: Create a virtual environment (recommended)
------------------------------------
  Inside the extracted folder, run:

      python3 -m venv venv
      source venv/bin/activate

  Your terminal prompt will now show "(venv)" to confirm it is active.

Step 4: Install dependencies
------------------------------------
      pip install -r requirements.txt

  Wait for all packages to download and install.

Step 5: Configure the application
------------------------------------
  Copy the example configuration file:

      cp .env.example .env

  Open .env with any text editor (TextEdit, nano, VS Code, etc.):

      nano .env

  At minimum, set these two values:

      LOOKOUT_APPLICATION_KEY=<paste your Lookout API key here>
      SECRET_KEY=<any long random string, e.g. output of: python3 -c "import secrets; print(secrets.token_hex(32))">

  Save and close the file.

Step 6: Start the dashboard
------------------------------------
      python3 run_dashboard.py

  The dashboard will start and automatically open your browser to:
      http://127.0.0.1:5001

  To stop the server, press Ctrl+C in Terminal.

Step 7: Subsequent launches
------------------------------------
  Each time you open a new Terminal session, re-activate the virtual
  environment before starting:

      cd ~/Downloads/lookout-mra-dashboard
      source venv/bin/activate
      python3 run_dashboard.py


================================================================================
  SECTION 2 — INSTALLATION ON WINDOWS 11
================================================================================

Step 1: Verify Python is installed
------------------------------------
  Open Command Prompt (search "cmd" in the Start menu) and run:

      python --version

  You should see Python 3.8 or later.

  If Python is not installed:
    a) Open the Microsoft Store and search for "Python 3.12", then install it.
       -- OR --
    b) Download the installer from https://www.python.org/downloads/
       IMPORTANT: On the first installer screen, check the box
       "Add Python to PATH" before clicking Install.

Step 2: Extract the package
------------------------------------
  Right-click the ZIP file and select "Extract All...".
  Choose a destination (e.g. your Desktop or Documents folder).
  Open Command Prompt and navigate to the extracted folder:

      cd "%USERPROFILE%\Desktop\lookout-mra-dashboard"

  (Adjust the path to wherever you extracted it.)

Step 3: Create a virtual environment (recommended)
------------------------------------
      python -m venv venv
      venv\Scripts\activate

  Your prompt will now show "(venv)" to confirm it is active.

  If you see a script execution error, run this once to allow scripts:

      Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

  Then retry:  venv\Scripts\activate

Step 4: Install dependencies
------------------------------------
      pip install -r requirements.txt

  Wait for all packages to download and install.

Step 5: Configure the application
------------------------------------
  Copy the example configuration file:

      copy .env.example .env

  Open .env with Notepad or any text editor:

      notepad .env

  At minimum, set these two values:

      LOOKOUT_APPLICATION_KEY=<paste your Lookout API key here>
      SECRET_KEY=<any long random string>

  To generate a strong SECRET_KEY, run:

      python -c "import secrets; print(secrets.token_hex(32))"

  Copy the output and paste it as the SECRET_KEY value in .env.
  Save and close Notepad.

Step 6: Start the dashboard
------------------------------------
      python run_dashboard.py

  The dashboard will start and automatically open your browser to:
      http://127.0.0.1:5001

  To stop the server, press Ctrl+C in Command Prompt.

Step 7: Subsequent launches
------------------------------------
  Each time you open a new Command Prompt session, re-activate the
  virtual environment before starting:

      cd "%USERPROFILE%\Desktop\lookout-mra-dashboard"
      venv\Scripts\activate
      python run_dashboard.py


================================================================================
  SECTION 3 — CONFIGURATION REFERENCE
================================================================================

All settings are controlled by your .env file. The key settings are:

  LOOKOUT_APPLICATION_KEY   Your Lookout MRA API key (required for live data)
  SECRET_KEY                Random secret for session security (required)
  USE_SAMPLE_DATA           Set to "true" to run with built-in sample data
                            (no API key needed — good for testing the UI)

Authentication (disabled by default for local desktop use):
  AUTH_ENABLED              "true" to require login, "false" to skip (default)
  AUTH_USERS                Credentials in format "admin:password,user:pass2"

Cache Settings:
  CACHE_ENABLED             "true" to enable in-memory caching (recommended)
  CACHE_MAX_AGE_MINUTES     How long cache is valid (default: 60 minutes)
  ENABLE_DISK_CACHE         "true" to persist cache to SQLite across restarts
  BACKGROUND_REFRESH_ENABLED  "true" to auto-refresh cache in background

Multi-Tenant Mode:
  ENABLE_MULTI_TENANT       "true" to manage multiple Lookout accounts
  TENANTS_CONFIG_FILE       Path to tenants.json (see tenants.json.example)

Fleet Size Recommendations:
  Small  (<1,000 devices):   CACHE_MAX_AGE_MINUTES=30, ENABLE_DISK_CACHE=false
  Medium (1K-10K devices):   CACHE_MAX_AGE_MINUTES=60, ENABLE_DISK_CACHE=true
  Large  (10K+ devices):     CACHE_MAX_AGE_MINUTES=120, ENABLE_DELTA_SYNC=true

Server Settings:
  HOST                      Bind address (default: 127.0.0.1 — localhost only)
  PORT                      Port number (default: 5001)
  LOG_LEVEL                 DEBUG, INFO, WARNING, ERROR (default: INFO)


================================================================================
  SECTION 4 — MULTI-TENANT SETUP
================================================================================

To manage multiple Lookout accounts (tenants) from one dashboard:

  1. Copy the example tenants file:
       macOS:    cp tenants.json.example tenants.json
       Windows:  copy tenants.json.example tenants.json

  2. Edit tenants.json and add your tenant entries. Each tenant requires:
       - tenant_id:              A unique identifier (e.g. "acme_corp")
       - tenant_name:            Display name shown in the dashboard
       - lookout_application_key: That tenant's Lookout API key
       - enabled:                true or false

  3. In .env, enable multi-tenant mode:
       ENABLE_MULTI_TENANT=true
       TENANTS_CONFIG_FILE=./tenants.json

  4. Restart the dashboard.


================================================================================
  SECTION 5 — RUNNING WITH SAMPLE DATA (NO API KEY REQUIRED)
================================================================================

To explore the dashboard without a Lookout API key:

  1. In .env, set:
       USE_SAMPLE_DATA=true

  2. Start the dashboard normally:
       python3 run_dashboard.py     (macOS)
       python run_dashboard.py      (Windows)

  The dashboard will load built-in sample device data so you can explore
  all features including filtering, export, and risk analysis.


================================================================================
  SECTION 6 — TROUBLESHOOTING
================================================================================

Problem:  "python" or "python3" not found
Solution: Install Python from https://www.python.org/downloads/
          On Windows, ensure "Add Python to PATH" is checked during install.
          Restart your terminal after installing.

Problem:  "pip install" fails or packages not found
Solution: Ensure your virtual environment is active (you see "(venv)" in the
          prompt). If not, run:
            macOS:    source venv/bin/activate
            Windows:  venv\Scripts\activate

Problem:  Port 5001 already in use
Solution: Change the port in .env:
            PORT=5002
          Then access the dashboard at http://127.0.0.1:5002

Problem:  "No module named 'flask'" after install
Solution: The virtual environment may not be active. Run:
            macOS:    source venv/bin/activate
            Windows:  venv\Scripts\activate
          Then try starting again.

Problem:  Browser does not open automatically
Solution: Manually open your browser and go to:
            http://127.0.0.1:5001

Problem:  API authentication errors / no devices loading
Solution: - Verify your LOOKOUT_APPLICATION_KEY in .env is correct
          - Confirm your API key has not expired in the Lookout admin console
          - Check your internet connection
          - Try setting USE_SAMPLE_DATA=true to confirm the app runs correctly

Problem:  Export to Excel fails
Solution: - Ensure the /tmp directory (macOS/Linux) or temp folder (Windows)
            is writable
          - Check the dashboard log for details (dashboard.log)

Problem:  Windows — "execution of scripts is disabled" error
Solution: Run PowerShell as Administrator and execute:
            Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
          Then retry activating the virtual environment.


================================================================================
  SECTION 7 — UNINSTALLING
================================================================================

macOS:
  Simply delete the extracted folder and its contents:
      rm -rf ~/Downloads/lookout-mra-dashboard

Windows:
  Delete the extracted folder from wherever you placed it (Desktop,
  Documents, etc.). No registry entries or system files are created.


================================================================================
  SUPPORT
================================================================================

  For assistance, contact:  frank.gravato@lookout.com

  When reporting an issue, please include:
    - Your operating system and version
    - Python version (python --version or python3 --version)
    - The error message or unexpected behavior observed
    - Relevant lines from dashboard.log (located in the app folder)

================================================================================

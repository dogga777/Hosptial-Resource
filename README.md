# HN-AI-05 — Cross-Hospital Resource Rebalancer

A beginner-friendly hackathon web application for predicting hospital oxygen-cylinder shortages and recommending transfers between hospitals.

## Stack

- Frontend: HTML + CSS + JavaScript
- Backend: Python FastAPI
- Database: MongoDB Atlas
- Recommendation explanation: demo response (Gemini is not currently connected)
- Deployment: Render
- Simulation: Python-generated live feed

## Architecture

Simulator -> FastAPI -> MongoDB
                    |
                    +-> Trend Predictor
                    |
                    +-> Rebalancer + travel ETA
                    |
                    +-> Transfer explanation (demo)
                    |
                    +-> Web Dashboard

## Local setup on Windows PowerShell

### 1. Open the project

```powershell
cd C:\path\to\hospital-rebalancer
```

### 2. Create a virtual environment

```powershell
py -3.11 -m venv .venv
```

### 3. Activate it

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 4. Install packages

```powershell
pip install -r backend\requirements.txt
```

### 5. Configure environment

Copy:

```text
backend\.env.example
```

to:

```text
backend\.env
```

Then put your MongoDB Atlas URI in `.env`. A Gemini API key is not required;
the explanation endpoint currently returns a demo response.

### 6. Start FastAPI

```powershell
uvicorn backend.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/app
```

### 7. Seed data

Click "Seed Demo" in the dashboard, or run:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/seed
```

### 8. Generate live updates

Click "Simulate demand" or use:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/simulate
```

The dashboard refreshes every 5 seconds.

### Automatic simulated oxygen transfers

Use **Detect & transfer** to check current stock without changing demand, or
**Simulate demand** to decrease stock and run the same shortage check. When a
hospital has less than six hours of oxygen remaining, the rebalancer finds a
donor that can spare cylinders while keeping the configured safety reserve (twelve hours by default). It moves
enough whole cylinders to bring the receiving hospital toward a six-hour
buffer, updates both hospitals' database stock, and records the simulated
transfer in the dashboard.

To run the shortage check directly:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/auto-transfer
```

This is a demo-only inventory simulation. It does not arrange real transport or
dispatch oxygen to hospitals.

## What the demo proves

1. Hospital A can be predicted to become short.
2. Hospital B can have surplus stock.
3. The system compares hospitals instead of viewing them separately.
4. The transfer algorithm checks distance and travel time.
5. A recommendation contains source, destination, quantity and ETA.
6. A hold-out check provides a simple model accuracy signal.
7. The dashboard displays a demo explanation for each transfer.

## Render deployment

### Before deploying

1. Push this project folder to a GitHub repository. Keep `backend\.env` and
   `.venv` out of Git; they are excluded by `.gitignore`.
2. Create a MongoDB Atlas database and a database user with read/write access
   to the application database. In Atlas **Network Access**, allow Render's
   outbound connections (Atlas commonly requires `0.0.0.0/0` for Render's
   dynamic IPs). Use a dedicated database user and a strong password.
3. Ensure `render.yaml` is at the root of the GitHub repository. If this
   project is inside a larger repository, set its folder as Render's Blueprint
   path and service root directory.

### Deploy using the Blueprint

1. In Render, choose **New + → Blueprint** and connect the GitHub repository.
2. Review the `hospital-rebalancer` web service from `render.yaml`.
3. When prompted for `MONGO_URI`, paste the MongoDB Atlas connection URI.
   Do not commit this URI to GitHub or put it in `render.yaml`.
4. Apply the Blueprint and wait for the build and `/healthz` check to pass.

The Blueprint installs the backend dependencies and starts the frontend and API
on the same Render web service:

Build command:

```text
pip install -r backend/requirements.txt
```

Start command:

```text
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Render reads `DB_NAME` and the simulation settings from `render.yaml`. The only
required secret is `MONGO_URI`; no Gemini key is needed for the current demo.
Once the service is live:

1. Open `https://YOUR-RENDER-SERVICE.onrender.com/`; it redirects to the UI.
2. Check `https://YOUR-RENDER-SERVICE.onrender.com/healthz` for the health
   response.
3. Click **Seed demo** once to initialize the hospital inventory.
4. Use **Detect & transfer** or **Simulate demand** to exercise transfers.

The dashboard and API are served by the same service; no separate frontend
hosting or CORS configuration is needed.

### Updating the deployment

Push changes to the connected GitHub branch. Render will build and deploy the
updated frontend and backend automatically.

## Important demo limitation

The hospital values are simulated, not real hospital data. The application is a hackathon prototype and should not be used for real clinical logistics without validation, authorization, safety controls and verified operational data.

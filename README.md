# Havenly Hospitality

Smart Hospitality Guest Service & Workforce Management System for SIH26199.

## What is included

- React + Vite + TypeScript responsive operations workspace
- FastAPI REST service with SQLAlchemy and SQLite
- JWT authentication with guest, staff, and manager roles
- Category-to-department and skill routing
- Lowest-workload available staff assignment
- Waiting queue notifications when no qualified staff is available
- Request status lifecycle and guest notifications
- Feedback endpoint for completed requests
- Seeded demo users, departments, skills, and staff

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The backend creates `hospitality.db`, its tables, and demo data automatically on startup. Copy `backend/.env.example` to `backend/.env` when you need to configure the database, JWT secret, or frontend origin.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Copy `frontend/.env.example` to `frontend/.env` to set `VITE_API_BASE_URL`. The default is `http://localhost:8000`.

Open `http://localhost:5173`.

Demo credentials use password `demo123`:

- Manager: `manager@havenly.demo`
- Guest: `guest@havenly.demo`
- Staff: `ravi@havenly.demo`

The client role switcher signs in as the corresponding seeded demo user and loads live data from the API. The API login is available at `POST /auth/login` using OAuth2 form fields (`username`, `password`). Swagger docs are available at `http://localhost:8000/docs`.

## Demo flow

1. Start the backend, then start the frontend in separate terminals.
2. Use the Guest role, choose `AC or fan`, and submit a request for room 205.
3. The API classifies it as `Maintenance + HVAC`, assigns suitable available staff, and creates staff and guest notifications.
4. Use the Staff role to accept, start, and complete the task. Switch back to Guest to see the completed status.
5. Use the Manager role to see live totals, workload, availability, and unassigned requests.

## Deployment

### Vercel

Set the frontend environment variable `VITE_API_URL` to the Render API URL and deploy the `frontend` directory with the Vite preset.

### Render

Create a Web Service from the repository, set the root directory to `backend`, build command to `pip install -r requirements.txt`, and start command to `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `DATABASE_URL`, `JWT_SECRET`, and `FRONTEND_URL` in Render environment variables. SQLite is suitable for a demo; use a managed PostgreSQL database for production scale.

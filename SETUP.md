
## Versions

python --> >=3.12
postgresql  --> 16 or 17


## Database
Login to psql: psql -U postgres
Database creatation: CREATE DATABASE {database_name};
Connect to created Database: \c {database_name}


## Env varibales and installition
cp .env.example .env
uv venv
activate venv
uv add -r requiements.txt

## LLM provide and model
Provider -> Groq
Model -> we use "openai/gpt-oss-120b"


## Run
uv run uvicorn server.main:app --reload 

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs

Tables are created on startup. There is no separate migration command. Start this API before the React app.

Uploaded files go to `uploads/` unless `UPLOAD_DIR` is set. `CORS_ORIGINS` must include the React dev origin (`http://127.0.0.1:5173` and `http://localhost:5173` are already listed).

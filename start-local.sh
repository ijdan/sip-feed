#!/bin/bash
BASE="$(cd "$(dirname "$0")" && pwd)"

echo "Démarrage du backend (port 8000)..."
cd "$BASE/backend"
source venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Démarrage du frontend (port 3000)..."
cd "$BASE/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Services démarrés :"
echo "  Backend  → http://localhost:8000"
echo "  API docs → http://localhost:8000/docs"
echo "  Frontend → http://localhost:3000"
echo ""
echo "Ctrl+C pour tout arrêter."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

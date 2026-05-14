#!/bin/bash
# Exécute tous les tests fonctionnels et affiche un rapport

BASE="$(cd "$(dirname "$0")/.." && pwd)"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Tests fonctionnels — Sip-feed                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Vérification services locaux
check_service() {
  local name=$1 url=$2
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
  if [ "$CODE" = "200" ]; then
    echo -e "  ${GREEN}✓ $name UP${NC}"
    return 0
  else
    echo -e "  ${RED}✗ $name DOWN (HTTP $CODE)${NC}"
    return 1
  fi
}

echo "Services :"
BACKEND_OK=0; FRONTEND_OK=0
check_service "Backend  (8000)" "http://localhost:8000/health" && BACKEND_OK=1
check_service "Frontend (3000)" "http://localhost:3000"       && FRONTEND_OK=1
echo ""

if [ "$BACKEND_OK" -eq 0 ]; then
  echo -e "${YELLOW}⚠ Backend non disponible — tests API ignorés${NC}"
fi

# Installation des dépendances de test
VENV="$BASE/tests/.venv"
if [ ! -d "$VENV" ]; then
  echo "Installation des dépendances de test..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install pytest httpx pyjwt python-dotenv --quiet
  # Dépendances du collector
  "$VENV/bin/pip" install -r "$BASE/collector/requirements.txt" --quiet
fi

# Variables d'environnement
source "$VENV/bin/activate"
export API_URL="http://localhost:8000"
export FRONTEND_URL="http://localhost:3000"
export PYTHONPATH="$BASE/collector"
# Utiliser l'émulateur Firestore si disponible
export GRPC_DNS_RESOLVER=native
if curl -s http://localhost:8080 >/dev/null 2>&1; then
  export FIRESTORE_EMULATOR_HOST=localhost:8080
fi

# Exécution des tests
cd "$BASE/tests"
echo "Lancement des tests..."
echo ""

ARGS="-v --tb=short --no-header"
RESULTS=()
TOTAL_PASS=0; TOTAL_FAIL=0; TOTAL_SKIP=0

run_suite() {
  local name=$1 file=$2
  echo -e "${YELLOW}━━━ $name ━━━${NC}"
  OUTPUT=$("$VENV/bin/pytest" $file $ARGS 2>&1)
  echo "$OUTPUT" | grep -E "PASSED|FAILED|ERROR|SKIP|passed|failed|error" | tail -20
  PASS=$(echo "$OUTPUT" | grep -c " PASSED" || true)
  FAIL=$(echo "$OUTPUT" | grep -c " FAILED\| ERROR" || true)
  SKIP=$(echo "$OUTPUT" | grep -c " SKIPPED" || true)
  TOTAL_PASS=$((TOTAL_PASS + PASS))
  TOTAL_FAIL=$((TOTAL_FAIL + FAIL))
  TOTAL_SKIP=$((TOTAL_SKIP + SKIP))
  if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}✗ $FAIL échec(s)${NC}"
    echo "$OUTPUT" | grep -A5 "FAILED\|ERROR" | grep -v "^--"
  else
    echo -e "  ${GREEN}✓ $PASS test(s) passés${NC}"
  fi
  echo ""
}

run_suite "Tests API" "test_api.py"
run_suite "Tests Scraper" "test_scraper.py"
run_suite "Tests Collector" "test_collector.py"

# Résumé
TOTAL=$((TOTAL_PASS + TOTAL_FAIL + TOTAL_SKIP))
echo "══════════════════════════════════════════════════"
echo -e "  Total : ${GREEN}$TOTAL_PASS passés${NC} | ${RED}$TOTAL_FAIL échoués${NC} | $TOTAL_SKIP ignorés / $TOTAL tests"
if [ "$TOTAL_FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}✅ Tous les tests passent — non-régression OK${NC}"
  echo ""
  exit 0
else
  echo -e "  ${RED}❌ $TOTAL_FAIL test(s) en échec — push et déploiement bloqués${NC}"
  echo ""
  exit 1
fi

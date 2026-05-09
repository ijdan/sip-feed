#!/bin/bash
set -euo pipefail

GCLOUD=~/google-cloud-sdk/bin/gcloud
PROJECT=tech-news-aggregator-001
REGION=europe-west1
REGISTRY=europe-west1-docker.pkg.dev/$PROJECT/tech-news-repo

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICES=("${@:-backend frontend collector}")
if [ $# -eq 0 ]; then
  SERVICES=(backend frontend collector)
else
  SERVICES=("$@")
fi

RESULTS=()

run() {
  local label="$1"; shift
  local logfile="/tmp/deploy_${label// /_}.log"
  echo -e "\n${YELLOW}▶ $label...${NC}"
  if "$@" > "$logfile" 2>&1; then
    echo -e "${GREEN}✓ $label OK${NC}"
    RESULTS+=("✓ $label")
  else
    echo -e "${RED}✗ $label ERREUR${NC}"
    echo "--- Dernières lignes ---"
    tail -20 "$logfile"
    RESULTS+=("✗ $label")
  fi
}

for SERVICE in "${SERVICES[@]}"; do
  case $SERVICE in
    backend)
      run "Build backend" \
        $GCLOUD builds submit \
          --config=infrastructure/cloudbuild-backend.yaml \
          --project=$PROJECT

      run "Deploy backend" \
        $GCLOUD run deploy backend \
          --image=$REGISTRY/backend:latest \
          --region=$REGION \
          --platform=managed \
          --allow-unauthenticated \
          --set-env-vars="FIRESTORE_PROJECT_ID=$PROJECT,GRPC_DNS_RESOLVER=native,JWT_ALGORITHM=HS256,JWT_EXPIRE_MINUTES=1440" \
          --set-secrets="GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,JWT_SECRET=JWT_SECRET:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest" \
          --project=$PROJECT
      ;;

    frontend)
      run "Build frontend" \
        $GCLOUD builds submit \
          --config=infrastructure/cloudbuild-frontend.yaml \
          --project=$PROJECT

      run "Deploy frontend" \
        $GCLOUD run deploy frontend \
          --image=$REGISTRY/frontend:latest \
          --region=$REGION \
          --platform=managed \
          --allow-unauthenticated \
          --set-env-vars="NEXTAUTH_URL=https://frontend-o3hq6ak3ka-ew.a.run.app" \
          --set-secrets="GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,NEXTAUTH_SECRET=NEXTAUTH_SECRET:latest" \
          --project=$PROJECT
      ;;

    collector)
      run "Build collector" \
        $GCLOUD builds submit \
          --config=infrastructure/cloudbuild-collector.yaml \
          --project=$PROJECT

      run "Update collector job" \
        $GCLOUD run jobs update collector \
          --image=$REGISTRY/collector:latest \
          --region=$REGION \
          --project=$PROJECT
      ;;

    *)
      echo -e "${RED}Service inconnu : $SERVICE (valeurs : backend, frontend, collector)${NC}"
      ;;
  esac
done

echo -e "\n========== RÉSUMÉ =========="
for r in "${RESULTS[@]}"; do
  if [[ $r == ✓* ]]; then
    echo -e "${GREEN}$r${NC}"
  else
    echo -e "${RED}$r${NC}"
  fi
done

# Vérification santé post-déploiement
echo -e "\n========== SANTÉ =========="
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://backend-159654598910.europe-west1.run.app/health 2>/dev/null)
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://frontend-o3hq6ak3ka-ew.a.run.app 2>/dev/null)

[ "$BACKEND_STATUS" = "200" ] \
  && echo -e "${GREEN}✓ Backend : $BACKEND_STATUS${NC}" \
  || echo -e "${RED}✗ Backend : $BACKEND_STATUS${NC}"

[ "$FRONTEND_STATUS" = "200" ] \
  && echo -e "${GREEN}✓ Frontend : $FRONTEND_STATUS${NC}" \
  || echo -e "${RED}✗ Frontend : $FRONTEND_STATUS${NC}"

ARTICLES=$(curl -s https://backend-159654598910.europe-west1.run.app/articles/stats 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['total'])" 2>/dev/null || echo "?")
echo -e "  Articles en base : $ARTICLES"

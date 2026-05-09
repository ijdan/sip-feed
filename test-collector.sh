#!/bin/bash
BASE="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE/collector"
source venv/bin/activate

set -a && source .env && set +a

# Utilise l'émulateur Firestore local (pas la prod)
export FIRESTORE_EMULATOR_HOST="localhost:8080"
export GRPC_DNS_RESOLVER=native

echo "Lancement du collector en local..."
echo "(Émulateur Firestore local — prod NON modifiée)"
echo ""

python main.py

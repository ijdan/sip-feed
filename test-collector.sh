#!/bin/bash
BASE="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE/collector"
source venv/bin/activate

echo "Lancement du collector en local..."
echo "(Firestore de production utilisé)"
echo ""

set -a && source .env && set +a
GRPC_DNS_RESOLVER=native python main.py

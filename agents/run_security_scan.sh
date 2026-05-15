#!/bin/bash
# Script wrapper pour exécuter le scanner de sécurité

set -e

echo "🔐 Lancement du scanner de sécurité..."
echo ""

cd "$(dirname "$0")/.." || exit 1

EXIT_CODE=0
python3 agents/security_scanner.py --output security-report.json || EXIT_CODE=$?

echo ""
echo "📄 Rapport généré: security-report.json"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Scan réussi"
else
    echo "❌ Vulnérabilités CRITIQUE détectées"
fi

exit $EXIT_CODE

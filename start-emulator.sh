#!/bin/bash
BASE="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE"

EXPORT_DIR="$BASE/.firestore-emulator-data"
mkdir -p "$EXPORT_DIR"

echo "Démarrage de l'émulateur Firestore (port 8080)..."
echo "Interface UI : http://localhost:4000"
echo ""
echo "Pour sauvegarder les données : ouvre un autre terminal et lance ./save-emulator.sh"
echo "Ctrl+C pour arrêter."
echo ""

if [ -f "$EXPORT_DIR/firestore_export/firestore_export.overall_export_metadata" ]; then
  echo "Restauration des données précédentes..."
  firebase emulators:start --only firestore --import="$EXPORT_DIR"
else
  echo "Démarrage vierge..."
  firebase emulators:start --only firestore
fi

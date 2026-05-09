#!/bin/bash
BASE="$(cd "$(dirname "$0")" && pwd)"
EXPORT_DIR="$BASE/.firestore-emulator-data"

echo "Sauvegarde des données de l'émulateur Firestore..."
rm -rf "$EXPORT_DIR"
firebase emulators:export "$EXPORT_DIR" --project tech-news-aggregator-001 --force 2>&1

if [ $? -eq 0 ]; then
  echo "Données sauvegardées dans $EXPORT_DIR"
else
  echo "Erreur : vérifie que l'émulateur est bien démarré sur le port 8080."
fi

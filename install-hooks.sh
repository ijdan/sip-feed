#!/bin/bash
# Installe les git hooks depuis tests/hooks/ vers .git/hooks/

ROOT="$(cd "$(dirname "$0")" && pwd)"
HOOKS_SRC="$ROOT/tests/hooks"
HOOKS_DST="$ROOT/.git/hooks"

echo "Installation des git hooks..."

for hook in "$HOOKS_SRC"/*; do
  name="$(basename "$hook")"
  chmod +x "$hook"
  ln -sf "$hook" "$HOOKS_DST/$name"
  echo "  ✓ $name installé"
done

echo ""
echo "Hooks actifs dans .git/hooks/ :"
ls -la "$HOOKS_DST" | grep -v "^total\|^d" | awk '{print "  "$9}'
echo ""
echo "Le sous-agent se déclenchera automatiquement à chaque 'git commit'."

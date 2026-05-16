#!/usr/bin/env python3
"""
Implémente le code applicatif d'une feature jusqu'à ce que ses tests d'acceptance
passent, ou jusqu'à épuisement du budget de turns (par défaut 15).

Boucle agentique avec tool use Claude API :
  - read_file(path)
  - write_file(path, content)
  - edit_file(path, old_string, new_string)
  - run_pytest(test_path)
  - list_directory(path)

Périmètre d'écriture restreint à `backend/app/features/<slug>/` (et le test
correspondant si Claude doit corriger une erreur de step definition).

Usage :
    python scripts/implement_feature.py features/hello.feature

Exit code :
    0 = tests d'acceptance verts
    1 = max-turns atteint sans succès (tests toujours rouges)
    2 = erreur fatale (config / fichier introuvable / API en erreur)

Variables d'environnement :
    ANTHROPIC_API_KEY : clé API Anthropic
    MAX_TURNS         : optionnel, défaut 15
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-opus-4-7"
MAX_TURNS_DEFAULT = 15
MAX_TOKENS_PER_TURN = 8192
PYTEST_TIMEOUT_SEC = 90
REPO_ROOT = Path.cwd()

ALLOWED_WRITE_PREFIXES = (
    "backend/app/features/",
    "tests/acceptance/",
)

TOOLS = [
    {
        "name": "read_file",
        "description": "Lit le contenu intégral d'un fichier dans le repo. Chemin relatif obligatoire.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin relatif au repo, ex. 'features/foo.feature'."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Écrit (ou écrase) un fichier. Écriture autorisée uniquement sous "
            "backend/app/features/ ou tests/acceptance/."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Remplace une chaîne précise par une autre dans un fichier existant. "
            "old_string doit être unique dans le fichier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "run_pytest",
        "description": (
            "Exécute pytest sur le chemin donné (typiquement le test d'acceptance). "
            "Retourne stdout+stderr (tronqué) et l'exit code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "test_path": {"type": "string", "description": "Chemin du fichier ou répertoire de test."},
            },
            "required": ["test_path"],
        },
    },
    {
        "name": "list_directory",
        "description": "Liste les entrées d'un répertoire (non récursif).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
]


def slugify(feature_path: Path) -> str:
    stem = feature_path.stem
    return re.sub(r"[^a-z0-9_]+", "_", stem.lower()).strip("_")


def safe_relative_path(raw: str) -> Path | None:
    """Refuse les chemins absolus ou hors du repo."""
    p = Path(raw)
    if p.is_absolute() or ".." in p.parts:
        return None
    return p


def tool_read_file(path: str) -> tuple[str, bool]:
    p = safe_relative_path(path)
    if p is None:
        return f"Erreur : chemin invalide '{path}'", True
    if not p.exists():
        return f"Erreur : fichier introuvable '{path}'", True
    try:
        content = p.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Erreur de lecture : {exc}", True
    # Limite pour éviter d'exploser le contexte
    if len(content) > 16000:
        content = content[:16000] + "\n... [TRONQUÉ]"
    return content, False


def tool_write_file(path: str, content: str) -> tuple[str, bool]:
    p = safe_relative_path(path)
    if p is None:
        return f"Erreur : chemin invalide '{path}'", True
    rel = str(p)
    if not any(rel.startswith(pref) for pref in ALLOWED_WRITE_PREFIXES):
        return f"Erreur : écriture refusée hors de {ALLOWED_WRITE_PREFIXES}", True
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Écrit {len(content)} caractères dans {p}", False


def tool_edit_file(path: str, old_string: str, new_string: str) -> tuple[str, bool]:
    p = safe_relative_path(path)
    if p is None:
        return f"Erreur : chemin invalide '{path}'", True
    rel = str(p)
    if not any(rel.startswith(pref) for pref in ALLOWED_WRITE_PREFIXES):
        return f"Erreur : édition refusée hors de {ALLOWED_WRITE_PREFIXES}", True
    if not p.exists():
        return f"Erreur : fichier introuvable '{path}'", True
    content = p.read_text(encoding="utf-8")
    count = content.count(old_string)
    if count == 0:
        return "Erreur : old_string introuvable dans le fichier", True
    if count > 1:
        return f"Erreur : old_string apparaît {count} fois, ambigüité", True
    p.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
    return f"Édité {p} (1 occurrence remplacée)", False


def tool_run_pytest(test_path: str) -> tuple[str, bool]:
    p = safe_relative_path(test_path)
    if p is None:
        return f"Erreur : chemin invalide '{test_path}'", True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(p), "-v", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SEC,
            cwd=REPO_ROOT,
        )
        out = (result.stdout + "\n" + result.stderr).strip()
        if len(out) > 8000:
            out = out[:4000] + "\n... [TRONQUÉ] ...\n" + out[-4000:]
        is_error = result.returncode != 0
        prefix = f"Exit code : {result.returncode} ({'ÉCHEC' if is_error else 'SUCCÈS'})\n"
        return prefix + out, False  # is_error=False car ce n'est pas une erreur de tool
    except subprocess.TimeoutExpired:
        return f"Erreur : pytest a dépassé {PYTEST_TIMEOUT_SEC}s", True
    except Exception as exc:
        return f"Erreur d'exécution pytest : {exc}", True


def tool_list_directory(path: str) -> tuple[str, bool]:
    p = safe_relative_path(path)
    if p is None:
        return f"Erreur : chemin invalide '{path}'", True
    if not p.exists():
        return f"Erreur : répertoire introuvable '{path}'", True
    if not p.is_dir():
        return f"Erreur : '{path}' n'est pas un répertoire", True
    entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
    return "\n".join(entries) or "(vide)", False


TOOL_HANDLERS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "run_pytest": tool_run_pytest,
    "list_directory": tool_list_directory,
}


def handle_tool_call(name: str, params: dict) -> tuple[str, bool]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"Erreur : tool inconnu '{name}'", True
    try:
        return handler(**params)
    except TypeError as exc:
        return f"Erreur : paramètres incorrects pour {name} : {exc}", True


SYSTEM_PROMPT = """Tu es un développeur Python senior expert en pytest-bdd v7+ et FastAPI.

Mission : implémenter le code applicatif d'une feature Gherkin pour que ses
tests d'acceptance passent. Tu disposes de tools pour lire, écrire et tester.

Périmètre d'écriture :
- `backend/app/features/<slug>/` : c'est ICI que va le code applicatif.
- `tests/acceptance/test_<slug>.py` : modifie-le uniquement si une step
  definition est cassée et empêche l'exécution. Ne modifie pas la logique
  des scénarios eux-mêmes.

Méthode :
1. Lis le .feature pour comprendre l'intention métier.
2. Lis le test d'acceptance pour voir les step definitions actuelles.
3. Lance pytest pour voir l'état initial.
4. Implémente le code minimal nécessaire.
5. Re-teste. Itère jusqu'au vert.

Conventions :
- Tout en français.
- Le moins de code possible. Pas d'abstraction prématurée.
- Si tu crées un nouveau module Python, ajoute un `__init__.py` à côté.
- Si tu modifies `backend/app/main.py` pour brancher un router, mentionne-le.

Quand les tests passent, dis « TESTS VERTS » et arrête.
"""


def build_initial_prompt(feature_path: Path, test_path: Path) -> str:
    return f"""Implémente le code applicatif pour la feature `{feature_path.name}`.

Fichiers de référence (lis-les avec read_file) :
- `{feature_path}` : la spec Gherkin.
- `{test_path}` : les step definitions pytest-bdd.

Le code applicatif doit aller dans `backend/app/features/{slugify(feature_path)}/`.

Commence par lire les deux fichiers, puis lance run_pytest sur `{test_path}`
pour voir l'état actuel. Implémente ensuite ce qu'il faut, puis re-teste.
Arrête-toi dès que pytest renvoie exit code 0 (réponds alors « TESTS VERTS »).
"""


def run_agent_loop(client: Anthropic, feature_path: Path, test_path: Path, max_turns: int) -> int:
    """
    Lance la boucle agentique. Retourne 0 si succès, 1 si max-turns sans succès.
    """
    messages: list[dict] = [
        {"role": "user", "content": build_initial_prompt(feature_path, test_path)},
    ]

    total_in_tokens = 0
    total_out_tokens = 0

    for turn in range(1, max_turns + 1):
        print(f"\n{'─' * 60}")
        print(f"Turn {turn}/{max_turns}")
        print("─" * 60)

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_PER_TURN,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        total_in_tokens += response.usage.input_tokens
        total_out_tokens += response.usage.output_tokens
        print(f"  tokens : in={response.usage.input_tokens}, out={response.usage.output_tokens} "
              f"(cumul in={total_in_tokens}, out={total_out_tokens})")

        # Append la réponse complète à l'historique (texte + tool_use)
        messages.append({"role": "assistant", "content": response.content})

        # Print les blocs texte pour visibilité
        for block in response.content:
            if block.type == "text":
                txt = block.text.strip()
                if txt:
                    print(f"  💬 {txt[:300]}")

        if response.stop_reason == "end_turn":
            print("  ✓ Claude a terminé (end_turn).")
            break

        if response.stop_reason != "tool_use":
            print(f"  ⚠ stop_reason inattendu : {response.stop_reason}")
            break

        # Exécute tous les tool_use du turn
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"  🔧 {block.name}({_format_input(block.input)})")
            output, is_error = handle_tool_call(block.name, block.input)
            preview = output[:200].replace("\n", " ↵ ")
            print(f"     {'✗' if is_error else '✓'} {preview}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})

    # À la fin du loop : vérification finale
    print(f"\n{'═' * 60}")
    print("Vérification finale : pytest")
    print("═" * 60)
    final_check, _ = tool_run_pytest(str(test_path))
    print(final_check)

    if "Exit code : 0" in final_check or final_check.startswith("Exit code : 0"):
        print(f"\n🟢 SUCCESS — tests d'acceptance verts en {turn} turn(s).")
        print(f"   Total tokens : in={total_in_tokens}, out={total_out_tokens}")
        return 0
    else:
        print(f"\n🔴 FAILURE — max_turns ({max_turns}) atteint, tests toujours rouges.")
        print(f"   Total tokens : in={total_in_tokens}, out={total_out_tokens}")
        return 1


def _format_input(d: dict) -> str:
    """Formate l'input d'un tool pour le log (tronqué)."""
    parts = []
    for k, v in d.items():
        s = str(v).replace("\n", "\\n")
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s!r}")
    return ", ".join(parts)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature", help="Chemin du fichier .feature à implémenter")
    parser.add_argument("--max-turns", type=int, default=int(os.environ.get("MAX_TURNS", MAX_TURNS_DEFAULT)))
    args = parser.parse_args(argv)

    feature_path = Path(args.feature)
    if not feature_path.exists():
        print(f"ERREUR : {feature_path} introuvable", file=sys.stderr)
        return 2

    slug = slugify(feature_path)
    test_path = Path(f"tests/acceptance/test_{slug}.py")
    if not test_path.exists():
        print(f"ERREUR : {test_path} introuvable (étape 1 n'a pas tourné ?)", file=sys.stderr)
        return 2

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERREUR : ANTHROPIC_API_KEY non défini", file=sys.stderr)
        return 2

    print(f"Implémentation de la feature : {feature_path}")
    print(f"Test associé              : {test_path}")
    print(f"Slug                      : {slug}")
    print(f"Modèle                    : {MODEL}")
    print(f"Max turns                 : {args.max_turns}")

    client = Anthropic(api_key=api_key)
    return run_agent_loop(client, feature_path, test_path, args.max_turns)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

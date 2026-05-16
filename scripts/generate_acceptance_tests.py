#!/usr/bin/env python3
"""
Génère les step definitions pytest-bdd à partir des fichiers .feature passés en argument.

Pour chaque .feature, on demande à Claude (claude-sonnet-4-6) de produire
le fichier de step definitions correspondant dans tests/acceptance/.

Idempotent : si le test correspondant existe déjà, on skip (sauf si --force).

Usage :
    python scripts/generate_acceptance_tests.py features/foo.feature [features/bar.feature ...]
    python scripts/generate_acceptance_tests.py --force features/foo.feature

Variables d'environnement requises :
    ANTHROPIC_API_KEY : clé API Anthropic (depuis console.anthropic.com)
"""
from __future__ import annotations

import os
import re
import sys
import argparse
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
ACCEPTANCE_DIR = Path("tests/acceptance")
FEATURES_DIR = Path("features")

SYSTEM_PROMPT = """Tu es un développeur Python expert en pytest-bdd v7+.

Génère uniquement du code Python du fichier de step definitions, sans préambule
ni explication, sans backticks markdown.

Conventions strictes du projet :
- Le code applicatif sera dans backend/app/features/<slug>/ (à importer après
  ajout du backend dans sys.path ou via un conftest.py qui le configure).
- Utiliser pytest-bdd v7+ syntax : `from pytest_bdd import scenarios, given, when, then, parsers`.
- En tête de fichier : `scenarios("../../features/<nom>.feature")` (chemin
  relatif depuis tests/acceptance/).
- Tous les steps (Given / When / Then) doivent être implémentés, même si
  pour l'instant le corps lève NotImplementedError (l'implémentation
  applicative viendra à l'étape suivante de la pipeline).
- Utiliser des fixtures pytest pour partager l'état entre steps (ex. context dict).
- Tout en français quand applicable (variables, messages d'erreur).
"""

USER_PROMPT_TEMPLATE = """Contenu de `{feature_path}` :

```gherkin
{feature_content}
```

Le fichier de sortie sera : `{output_path}`.
Le slug de la feature est : `{slug}` (utilise-le si tu dois importer du code
applicatif, par exemple `from app.features.{slug} import ...`).

Génère le contenu Python complet du fichier de step definitions. Réponds
UNIQUEMENT par du code Python sans backticks ni commentaire externe.
"""


def slugify(feature_path: Path) -> str:
    """Convertit `features/hello-world.feature` en `hello_world`."""
    stem = feature_path.stem
    return re.sub(r"[^a-z0-9_]+", "_", stem.lower()).strip("_")


def strip_markdown_fences(text: str) -> str:
    """Retire les backticks markdown si Claude en a mis malgré la consigne."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    lines = lines[1:]  # skip ouverture
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def generate_steps_for_feature(client: Anthropic, feature_path: Path, force: bool) -> Path | None:
    """
    Génère le fichier de step definitions pour un .feature.
    Retourne le chemin du fichier créé, ou None si skip.
    """
    if not feature_path.exists():
        print(f"⚠️  {feature_path} introuvable, skip")
        return None

    slug = slugify(feature_path)
    output_path = ACCEPTANCE_DIR / f"test_{slug}.py"

    if output_path.exists() and not force:
        print(f"✓ {output_path} existe déjà — skip (idempotent, utilise --force pour régénérer)")
        return None

    print(f"🤖 Génération des step definitions pour {feature_path}...")
    feature_content = feature_path.read_text(encoding="utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                feature_path=feature_path,
                feature_content=feature_content,
                output_path=output_path,
                slug=slug,
            ),
        }],
    )

    generated = strip_markdown_fences(response.content[0].text)
    ACCEPTANCE_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generated, encoding="utf-8")

    usage = response.usage
    print(
        f"  → écrit {output_path} "
        f"(in: {usage.input_tokens} tok / out: {usage.output_tokens} tok)"
    )
    return output_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "features",
        nargs="*",
        help="Chemins des fichiers .feature à traiter",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Régénérer même si le fichier de tests existe déjà",
    )
    args = parser.parse_args(argv)

    if not args.features:
        print("Aucun .feature passé en argument, rien à faire.")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERREUR : ANTHROPIC_API_KEY non défini dans l'environnement", file=sys.stderr)
        return 1

    client = Anthropic(api_key=api_key)
    generated_count = 0
    for feature_arg in args.features:
        feature_arg = feature_arg.strip()
        if not feature_arg:
            continue
        result = generate_steps_for_feature(client, Path(feature_arg), args.force)
        if result is not None:
            generated_count += 1

    print(f"\n✓ Terminé. {generated_count} fichier(s) de tests généré(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# Scanner de sécurité — Workflow CI automatique

## Contexte fonctionnel

L'agent de sécurité (`agents/security_scanner.py`) est un scanner statique Python qui analyse les fichiers `backend/app/**/*.py` selon 6 catégories de vulnérabilités (AUTH, INJ, EXP, ACC, ERR, VAL) × 4 sévérités (CRITIQUE/HAUTE/MOYENNE/BASSE). Un workflow GitHub Actions le déclenche sur chaque push main ou PR vers main qui touche le backend ; le job fail si une vuln CRITIQUE est détectée, bloquant le merge si protection rules activées.

## Objectif

- Empêcher l'ajout accidentel de patterns dangereux (`eval()`, `cursor.execute(f"SELECT {x}")`, `except: pass`) dans le backend.
- Tracer l'évolution des alertes au fil des commits (artifact JSON archivé).
- Servir de filet minimal en attendant l'adoption d'outils plus matures (bandit, semgrep).

## User Stories

### US-SEC-001 — Trigger automatique sur push backend

**En tant que** système,
**je veux** lancer le scanner à chaque push touchant `backend/app/**`,
**afin de** que les nouvelles vulnérabilités soient détectées dès le merge.

**Description fonctionnelle**
Workflow `.github/workflows/security-scan.yml`. Triggers :
- `on.push.branches: [main]`, paths : `backend/app/**`, `agents/security_scanner.py`, `.github/workflows/security-scan.yml`.
- `on.pull_request.branches: [main]`, mêmes paths.

Job `scan` sur `ubuntu-latest` : checkout v6, setup-python v6 (3.12), `python3 agents/security_scanner.py`, upload artifact JSON.

**Critères d'acceptation**
1. Un push sur main modifiant `backend/app/routers/articles.py` déclenche le workflow.
2. Un push modifiant uniquement `frontend/**` ne le déclenche pas.
3. Une PR vers main modifiant le backend déclenche le workflow comme check.
4. Le workflow apparaît dans l'onglet Actions avec statut visible.

---

### US-SEC-002 — Scanner les fichiers Python du backend

**En tant que** scanner,
**je veux** parcourir tous les `.py` sous `backend/app/`,
**afin de** détecter les patterns dangereux dans 6 catégories.

**Description fonctionnelle**
`SecurityScanner.scan_directory(backend/app)` :
1. Liste récursive des `.py`.
2. Pour chaque fichier, applique deux passes :
   - **Regex** : 6 catégories × 1-2 patterns chacune. Calcule numéro de ligne, filtre faux positifs via `_is_false_positive`, attribue severity.
   - **AST** : actuellement placeholder vide (`_analyze_ast` retiré "route sans docstring").
3. Append à `self.vulnerabilities`.

**Critères d'acceptation**
1. Tous les `.py` sous `backend/app/` sont scannés.
2. Pour chaque match valide → 1 entrée `Vulnerability` enregistrée.
3. Le scanner produit un total cohérent (vérifié manuellement).

---

### US-SEC-003 — Filtrage des faux positifs

**En tant que** scanner,
**je veux** filtrer les patterns évidents non-vulnérables,
**afin de** réduire le bruit pour l'équipe.

**Description fonctionnelle**
`_is_false_positive(category, line, context)` exclut :
- Lignes de commentaires (`#`) et imports.
- AUTH : routes `/health`, `/ping` ; ou présence de `Depends(` dans le fichier (proxy pour "auth FastAPI configurée").
- INJ : f-strings sans keyword SQL (`SELECT/INSERT/UPDATE/DELETE/FROM/WHERE/JOIN`) ni `.execute/.query/.raw` ni `eval/exec/compile`.

**Critères d'acceptation**
1. `f"Bearer {token}"` n'est PAS flagué CRITIQUE (filtre INJ).
2. `f"https://...{constant}"` n'est PAS flagué (filtre INJ).
3. Une route FastAPI avec `Depends(verify_jwt)` n'est PAS flaguée AUTH si `Depends(` apparaît ailleurs dans le fichier.
4. `cursor.execute(f"SELECT * FROM {table}")` reste flagué CRITIQUE.

**Limites connues**
- Si une route a `Depends` ailleurs mais que la route actuelle n'a pas d'auth → faux négatif silencieux (filtre trop laxe). Trade-off accepté.

---

### US-SEC-004 — Génération du rapport JSON

**En tant que** scanner,
**je veux** produire un rapport JSON structuré,
**afin de** qu'il soit consommable par d'autres outils et archivé en CI.

**Description fonctionnelle**
`generate_report()` retourne :
```json
{
  "timestamp": "2026-05-15T13:52:30",
  "total_vulnerabilities": 28,
  "by_severity": { "CRITIQUE": [], "HAUTE": [...], "MOYENNE": [...], "BASSE": [...] },
  "vulnerabilities": [ {file, line, category, severity, title, description, code_snippet} ]
}
```
Le fichier est écrit à `security-report.json` dans cwd.

**Critères d'acceptation**
1. Le fichier est créé après chaque scan.
2. Le format JSON est valide (parseable).
3. Toutes les vulns sont incluses dans `vulnerabilities[]` ET groupées dans `by_severity`.
4. Le fichier est uploadé en artifact GitHub (`actions/upload-artifact@v4`) avec `if: always()` (même en cas de fail).

---

### US-SEC-005 — Bloquer la CI si vulnérabilité CRITIQUE

**En tant que** scanner,
**je veux** retourner exit code 1 si au moins 1 CRITIQUE,
**afin de** que le check GitHub passe en rouge et bloque le merge (si protection rules activées).

**Description fonctionnelle**
Dans `main()` : si `len(critique) > 0` → `sys.exit(1)`. Sinon `sys.exit(0)`.

**Critères d'acceptation**
1. 0 CRITIQUE → exit 0 → check vert.
2. ≥ 1 CRITIQUE → exit 1 → check rouge.
3. Le contenu du rapport JSON est inchangé quel que soit l'exit code.
4. L'artifact est uploadé même en cas de fail (`if: always()`).

---

### US-SEC-006 — Wrapper shell pour exécution locale

**En tant que** développeur,
**je veux** exécuter le scanner sur ma machine avant de pousser,
**afin de** détecter les vulns en local et corriger avant que la CI fail.

**Description fonctionnelle**
`./agents/run_security_scan.sh` : se place à la racine du repo, lance `python3 agents/security_scanner.py`, capture l'exit code via `|| EXIT_CODE=$?` (compatible avec `set -e`).

**Critères d'acceptation**
1. Le script tourne sans erreur depuis n'importe quel répertoire (auto-cd).
2. Affiche le même résumé que la CI.
3. Génère `security-report.json` à la racine.
4. Affiche "✅ Scan réussi" ou "❌ Vulnérabilités CRITIQUE détectées" selon l'exit code.

---

### US-SEC-007 — Archive du rapport en artifact GitHub

**En tant que** auditeur,
**je veux** télécharger le rapport JSON d'un run passé,
**afin de** analyser l'historique des vulns.

**Description fonctionnelle**
`actions/upload-artifact@v4` avec `name: security-report`, `path: security-report.json`, `if-no-files-found: warn`, `if: always()`. Conservation par défaut GitHub (90 jours).

**Critères d'acceptation**
1. L'artifact est visible dans l'onglet Actions du run.
2. Téléchargeable via l'UI ou l'API.
3. Disponible même si le scanner a fail.

---

## Dépendances

- GitHub Actions runners ubuntu-latest.
- Python 3.12 standard library (`re`, `ast`, `json`, `enum`, `dataclasses`).
- `.github/workflows/security-scan.yml`.
- Repo public (runners gratuits illimités).

## Contraintes

- **Métier** : scanner statique uniquement. Pas de SAST avancé, pas de scan de dépendances, pas de comparaison CVE.
- **Faux positifs** : malgré les filtres, certaines alertes restent du bruit (AUTH avec `Depends` proche mais pas dans le même contexte). Documenté comme limite.
- **Faux négatifs** : un `eval(user_input)` avec un nom de variable surprenant pourrait passer. Pour une vraie défense, considérer `bandit` (~150 règles éprouvées) ou `semgrep`.
- **Évolutions** : la passe AST est un placeholder pour extensions futures (détection de `subprocess(shell=True)`, accès `request.body` direct sans Pydantic, etc.).

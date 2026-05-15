# 🔐 Agent de Sécurité — Sip-feed

Scanner automatisé de vulnérabilités déclenché à chaque push sur le backend.

## 📋 Fonctionnalités

- **6 catégories** de vulnérabilités détectées :
  - 🔴 **AUTH** — Authentification/autorisation manquantes
  - 🔴 **INJ** — Injections (SQL/NoSQL/commandes)
  - 🟠 **EXP** — Exposition de données sensibles
  - 🟡 **ACC** — Contrôles d'accès défaillants
  - 🔵 **ERR** — Gestion d'erreurs pauvre
  - 🔵 **VAL** — Validation d'entrée insuffisante

- **4 niveaux de sévérité** :
  - 🔴 **CRITIQUE** — Bloque le merge, patch immédiat requis
  - 🟠 **HAUTE** — Risque de sécurité majeur
  - 🟡 **MOYENNE** — À traiter dans la sprint
  - 🔵 **BASSE** — Amélioration de qualité

## 🚀 Utilisation

### Exécution locale

```bash
./agents/run_security_scan.sh
```

Cela générera un rapport JSON `security-report.json` avec tous les détails.

### Exécution depuis GitHub Actions

Le workflow s'active automatiquement quand vous poussez du code touchant :
- `backend/app/**`
- `backend/app/auth/**`
- `backend/app/routers/**`
- `backend/app/middleware.py`

### Résultats

Le scanner :
1. 📊 Affiche un résumé dans les logs
2. 💬 Commente sur les PRs avec les findings
3. 📄 Sauvegarde un rapport JSON
4. ❌ Bloque le merge si **vulnérabilités CRITIQUE** détectées

## 🔍 Patterns détectés

### AUTH (Authentification)
```python
# ❌ Mauvais
@app.get("/admin/settings")
def get_settings():
    return db.get_admin_config()

# ✅ Bon
@app.get("/admin/settings")
def get_settings(current_user: User = Depends(verify_admin)):
    return db.get_admin_config()
```

### INJ (Injection)
```python
# ❌ Mauvais (f-string)
query = f"SELECT * FROM users WHERE id = {user_id}"

# ✅ Bon (requête paramétrée)
from sqlalchemy import text
query = text("SELECT * FROM users WHERE id = :id").bindparams(id=user_id)
```

### EXP (Exposition)
```python
# ❌ Mauvais
logger.info(f"User login: {email}, password: {password}")

# ✅ Bon
logger.info(f"User login: {email}")
# Les passwords ne doivent JAMAIS être loggés
```

### VAL (Validation)
```python
# ❌ Mauvais
@app.post("/users")
def create_user(data: dict):
    return db.create(data)

# ✅ Bon
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    name: str

@app.post("/users")
def create_user(user: UserCreate):
    return db.create(user.dict())
```

## 📊 Structure du rapport

```json
{
  "timestamp": "2026-05-15T14:30:00+00:00",
  "total_vulnerabilities": 3,
  "by_severity": {
    "CRITIQUE": [...],
    "HAUTE": [
      {
        "file": "backend/app/routers/admin.py",
        "line": 42,
        "category": "AUTH — Authentification/Autorisation",
        "severity": "HAUTE",
        "title": "Endpoint sans dépendance d'authentification détectée",
        "description": "Vérifier que la route dispose d'un système d'authentification...",
        "code_snippet": "@app.delete('/admin/purge')"
      }
    ],
    "MOYENNE": [...],
    "BASSE": [...]
  },
  "vulnerabilities": [...]
}
```

## ⚙️ Configuration

### Modifier les règles de détection

Éditer `agents/security_scanner.py` :

```python
self.patterns = {
    VulnCategory.AUTH: [
        (r"votre_regex_ici", "Description du pattern"),
        # ...
    ],
    # ...
}
```

### Exclure des fichiers/patterns

Modifier `_is_false_positive()` :

```python
def _is_false_positive(self, category: VulnCategory, line: str, context: str) -> bool:
    if category == VulnCategory.AUTH and 'my_exception' in line:
        return True  # Ignorer ce pattern
    return False
```

## 📝 Conventions

- **Tous les messages en français** (aligné avec le projet)
- Les vulnérabilités CRITIQUE bloquent le merge
- Les rapports sont conservés 30 jours en artifacts
- Chaque PR reçoit un commentaire détaillé

## 🔧 Troubleshooting

### Le workflow ne se déclenche pas

Vérifier que vous poussez vers `main` et que vous touchez les fichiers listés dans `paths`.

### Faux positifs trop nombreux

Ajuster les regex ou ajouter des exceptions dans `_is_false_positive()`.

### Besoin d'ignorer une vulnérabilité

Ajouter un commentaire dans le code :
```python
# Security: exception acceptée pour cette raison
@app.get("/public")  # No auth required
def public_endpoint():
    pass
```

## 📚 Ressources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Pydantic Validation](https://docs.pydantic.dev/)

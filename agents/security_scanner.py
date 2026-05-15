#!/usr/bin/env python3
"""
Agent de scan de sécurité — Analyse les endpoints FastAPI pour détecter les vulnérabilités.

Catégories détectées :
  - AUTH : Authentification/autorisation manquantes
  - INJ : Injections SQL/NoSQL/commandes
  - EXP : Exposition de données sensibles
  - ACC : Contrôles d'accès défaillants
  - ERR : Gestion d'erreurs pauvre
  - VAL : Validation d'entrée insuffisante
"""

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from enum import Enum
from dataclasses import dataclass, asdict


class Severity(Enum):
    """Niveaux de sévérité des vulnérabilités."""
    CRITIQUE = "CRITIQUE"
    HAUTE = "HAUTE"
    MOYENNE = "MOYENNE"
    BASSE = "BASSE"


class VulnCategory(Enum):
    """Catégories de vulnérabilités."""
    AUTH = "AUTH — Authentification/Autorisation"
    INJ = "INJ — Injection (SQL/NoSQL/Commande)"
    EXP = "EXP — Exposition de données"
    ACC = "ACC — Contrôle d'accès"
    ERR = "ERR — Gestion d'erreur"
    VAL = "VAL — Validation d'entrée"


@dataclass
class Vulnerability:
    """Représentation d'une vulnérabilité détectée."""
    file: str
    line: int
    category: str
    severity: str
    title: str
    description: str
    code_snippet: str

    def to_dict(self):
        return asdict(self)


class SecurityScanner:
    """Scanner de sécurité pour endpoints FastAPI."""

    def __init__(self, backend_path: str):
        self.backend_path = Path(backend_path)
        self.vulnerabilities: List[Vulnerability] = []
        
        # Patterns de détection
        self.patterns = {
            VulnCategory.AUTH: [
                (r"@app\.get|@app\.post|@app\.put|@app\.delete|@router\.(get|post|put|delete)", 
                 "Endpoint sans dépendance d'authentification détectée"),
                (r"query.*=.*\(.*\)(?!.*Depends)", 
                 "Paramètre de requête non validé"),
            ],
            VulnCategory.INJ: [
                (r"f['\"].*\{.*\}.*['\"]|\.format\(.*\)", 
                 "Risque d'injection via f-string ou format()"),
                (r"\.query\(|\.execute\(|\.raw\(", 
                 "Requête SQL/NoSQL directe potentiellement dangereuse"),
            ],
            VulnCategory.EXP: [
                (r"print\(|logger\.(info|debug)\(.*(?:password|token|secret|key|api_key)", 
                 "Exposition potentielle de secrets en logs"),
                (r"except.*:[\s]*pass|except.*:[\s]*return", 
                 "Exception capturée silencieusement (exposition de stack trace)"),
            ],
            VulnCategory.VAL: [
                (r"request\.(?:query_params|form|json|body)(?!.*Pydantic|Field)", 
                 "Accès direct aux données sans validation Pydantic"),
                (r"eval\(|exec\(|compile\(", 
                 "Utilisation d'eval/exec (très dangereux)"),
            ],
            VulnCategory.ACC: [
                (r"require_admin|@admin_only|admin=True", 
                 "Vérification d'admin détectée mais structure à valider"),
            ],
            VulnCategory.ERR: [
                (r"except\s*:", 
                 "Capture d'exception générique (Exception non spécifiée)"),
                (r"raise.*(?:Exception|Error)\(", 
                 "Exception générique (considérer un type plus spécifique)"),
            ],
        }

    def scan_file(self, filepath: Path) -> None:
        """Analyse un fichier Python pour les vulnérabilités."""
        try:
            content = filepath.read_text(encoding='utf-8')
        except Exception as e:
            print(f"⚠️  Erreur lecture {filepath}: {e}", file=sys.stderr)
            return

        rel_path = str(filepath.relative_to(self.backend_path))
        lines = content.split('\n')

        # 1. Vérifier les patterns de regex
        for category, patterns in self.patterns.items():
            for pattern, description in patterns:
                try:
                    matches = list(re.finditer(pattern, content, re.MULTILINE | re.DOTALL))
                    for match in matches:
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                        
                        # Filtrer les faux positifs
                        if self._is_false_positive(category, line_content, content):
                            continue
                        
                        severity = self._determine_severity(category, description)
                        
                        self.vulnerabilities.append(Vulnerability(
                            file=rel_path,
                            line=line_num,
                            category=category.value,
                            severity=severity.value,
                            title=description,
                            description=self._get_full_description(category, description),
                            code_snippet=line_content.strip()[:100]
                        ))
                except re.error:
                    pass

        # 2. Analyse AST pour détections plus fines
        try:
            tree = ast.parse(content)
            self._analyze_ast(tree, rel_path, lines)
        except SyntaxError:
            pass

    def _is_false_positive(self, category: VulnCategory, line: str, context: str) -> bool:
        """Vérifie si c'est un faux positif."""
        # Ignorer les strings/commentaires
        if line.strip().startswith('#'):
            return True
        
        # Ignorer les imports
        if 'import' in line:
            return True
            
        # Certains patterns à exclure selon la catégorie
        if category == VulnCategory.AUTH:
            # Les endpoints de healthcheck ne besoin pas d'auth
            if 'health' in line.lower() or 'ping' in line.lower():
                return True
        
        return False

    def _determine_severity(self, category: VulnCategory, description: str) -> Severity:
        """Détermine la sévérité en fonction de la catégorie et description."""
        if category == VulnCategory.INJ or "eval" in description or "exec" in description:
            return Severity.CRITIQUE
        elif category in [VulnCategory.AUTH, VulnCategory.EXP]:
            return Severity.HAUTE
        elif category in [VulnCategory.ACC, VulnCategory.VAL]:
            return Severity.MOYENNE
        else:
            return Severity.BASSE

    def _analyze_ast(self, tree: ast.AST, filepath: str, lines: List[str]) -> None:
        """Analyse l'AST pour des patterns spécifiques."""
        for node in ast.walk(tree):
            # Détection de fonctions sans docstring
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not ast.get_docstring(node):
                        # Les routes FastAPI sans docstring
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call):
                                if isinstance(decorator.func, ast.Attribute):
                                    if decorator.func.attr in ['get', 'post', 'put', 'delete']:
                                        self.vulnerabilities.append(Vulnerability(
                                            file=filepath,
                                            line=node.lineno,
                                            category=VulnCategory.ERR.value,
                                            severity=Severity.BASSE.value,
                                            title="Route sans documentation",
                                            description="La route n'a pas de docstring (manque de documentation).",
                                            code_snippet=lines[node.lineno - 1].strip()[:100] if node.lineno <= len(lines) else ""
                                        ))

    def _get_full_description(self, category: VulnCategory, short_desc: str) -> str:
        """Génère une description complète avec recommandation."""
        descriptions = {
            VulnCategory.AUTH: "Vérifier que la route dispose d'un système d'authentification. Utiliser @Depends(verify_jwt) ou similaire.",
            VulnCategory.INJ: "Risque d'injection détecté. Toujours utiliser des requêtes paramétrées ou des ORM.",
            VulnCategory.EXP: "Danger d'exposition de données sensibles. Exclure passwords, tokens, secrets des logs.",
            VulnCategory.VAL: "Valider toujours l'entrée utilisateur via Pydantic models ou JSONSchema.",
            VulnCategory.ACC: "Vérifier que les contrôles d'accès sont correctement appliqués.",
            VulnCategory.ERR: "Capturer les exceptions spécifiques et logger proprement les erreurs.",
        }
        return descriptions.get(category, short_desc)

    def scan_directory(self, target_path: str = None) -> None:
        """Scanne récursivement le backend pour les fichiers Python."""
        if target_path is None:
            target_path = self.backend_path / "app"
        else:
            target_path = Path(target_path)

        if not target_path.exists():
            print(f"❌ Chemin inexistant: {target_path}", file=sys.stderr)
            return

        py_files = list(target_path.rglob("*.py"))
        if not py_files:
            print(f"⚠️  Aucun fichier Python trouvé dans {target_path}", file=sys.stderr)
            return

        for py_file in py_files:
            self.scan_file(py_file)

    def generate_report(self) -> Dict:
        """Génère le rapport de scan."""
        by_severity = {
            Severity.CRITIQUE.value: [],
            Severity.HAUTE.value: [],
            Severity.MOYENNE.value: [],
            Severity.BASSE.value: [],
        }
        
        for vuln in self.vulnerabilities:
            by_severity[vuln.severity].append(vuln.to_dict())

        return {
            "timestamp": os.popen("date -Iseconds 2>/dev/null || date").read().strip(),
            "total_vulnerabilities": len(self.vulnerabilities),
            "by_severity": by_severity,
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
        }

    def print_summary(self) -> None:
        """Affiche un résumé du scan."""
        print("\n" + "="*70)
        print("📋 RAPPORT DE SCAN DE SÉCURITÉ — Sip-feed")
        print("="*70 + "\n")

        if not self.vulnerabilities:
            print("✅ Aucune vulnérabilité détectée !\n")
            return

        by_severity = {}
        for vuln in self.vulnerabilities:
            if vuln.severity not in by_severity:
                by_severity[vuln.severity] = []
            by_severity[vuln.severity].append(vuln)

        for severity in [Severity.CRITIQUE, Severity.HAUTE, Severity.MOYENNE, Severity.BASSE]:
            vulns = by_severity.get(severity.value, [])
            if vulns:
                emoji = "🔴" if severity == Severity.CRITIQUE else \
                        "🟠" if severity == Severity.HAUTE else \
                        "🟡" if severity == Severity.MOYENNE else "🔵"
                print(f"{emoji} {severity.value} ({len(vulns)} trouvée(s))")
                for vuln in vulns:
                    print(f"   • {vuln.file}:{vuln.line} — {vuln.category}")
                    print(f"     {vuln.title}")
                print()

        print(f"📊 Total : {len(self.vulnerabilities)} vulnérabilité(s) détectée(s)\n")


def main():
    """Point d'entrée du scanner."""
    backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/backend"
    
    if len(sys.argv) > 1:
        backend_path = sys.argv[1]

    if not os.path.exists(backend_path):
        print(f"❌ Erreur : {backend_path} n'existe pas", file=sys.stderr)
        sys.exit(1)

    scanner = SecurityScanner(backend_path)
    scanner.scan_directory()
    scanner.print_summary()

    report = scanner.generate_report()
    
    # Sauvegarder le rapport JSON
    report_file = "security-report.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"📄 Rapport sauvegardé : {report_file}\n")

    # Exit avec code d'erreur si vulnérabilités critiques
    critical_count = len(report["by_severity"][Severity.CRITIQUE.value])
    if critical_count > 0:
        print(f"❌ {critical_count} vulnérabilité(s) CRITIQUE(s) détectée(s) !", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

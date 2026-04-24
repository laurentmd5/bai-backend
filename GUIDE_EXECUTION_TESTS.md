# GUIDE D'UTILISATION DES TESTS
## Testing Guide & Quick Commands

---

## 🚀 DÉMARRAGE RAPIDE

### 1. Configuration initiale
```bash
cd barrow-ai-backend

# Activer l'environnement virtuel
.\venv\Scripts\Activate.ps1

# Vérifier que pytest est installé
./venv/Scripts/pytest --version
```

### 2. Lancer tous les tests
```bash
./venv/Scripts/pytest tests/unit/ --ignore=tests/unit/test_output_validator.py -v
```

**Résultat attendu**:
```
======================= 69 passed in 1.34s ========================
```

---

## 📋 COMMANDES COURANTES

### Lancer tout
```bash
./venv/Scripts/pytest tests/unit/ -v
```

### Lancer un fichier spécifique
```bash
./venv/Scripts/pytest tests/unit/test_security.py -v
./venv/Scripts/pytest tests/unit/test_config.py -v
./venv/Scripts/pytest tests/unit/test_utils.py -v
```

### Lancer une classe de tests
```bash
./venv/Scripts/pytest tests/unit/test_security.py::TestJWT -v
./venv/Scripts/pytest tests/unit/test_security.py::TestPasswordHashing -v
./venv/Scripts/pytest tests/unit/test_security.py::TestTOTP -v
./venv/Scripts/pytest tests/unit/test_security.py::TestAESEncryption -v
```

### Lancer un test unique
```bash
./venv/Scripts/pytest tests/unit/test_security.py::TestJWT::test_create_access_token -v
./venv/Scripts/pytest tests/unit/test_security.py::TestPasswordHashing::test_verify_correct_password -v
```

### Mode rapide (sans verbose)
```bash
./venv/Scripts/pytest tests/unit/ -q
```

### Avec résumé court des erreurs
```bash
./venv/Scripts/pytest tests/unit/ --tb=short
```

### Avec résumé très court
```bash
./venv/Scripts/pytest tests/unit/ --tb=line
```

### Arrêter au premier échec
```bash
./venv/Scripts/pytest tests/unit/ -x
```

### Continuer après les 3 premiers échecs
```bash
./venv/Scripts/pytest tests/unit/ --maxfail=3
```

---

## 📊 RAPPORTS ET COUVERTURE

### Rapport de couverture complet
```bash
./venv/Scripts/pytest tests/unit/ --cov=app --cov-report=html --cov-report=term-missing
```
Ouvre: `htmlcov/index.html`

### Rapport de couverture terminal
```bash
./venv/Scripts/pytest tests/unit/ --cov=app --cov-report=term-missing
```

### Couverture module par module
```bash
./venv/Scripts/pytest tests/unit/ --cov=app.core.security --cov-report=term-missing
./venv/Scripts/pytest tests/unit/ --cov=app.core.config --cov-report=term-missing
./venv/Scripts/pytest tests/unit/ --cov=app.utils --cov-report=term-missing
```

### JSON report (pour CI/CD)
```bash
./venv/Scripts/pytest tests/unit/ --json-report --json-report-file=report.json
```

---

## 🔍 DEBUGGING

### Afficher les logs
```bash
./venv/Scripts/pytest tests/unit/ -v --log-cli-level=DEBUG
```

### Arrêter sur le premier failure et lancer debugger
```bash
./venv/Scripts/pytest tests/unit/ -x --pdb
```

### Afficher les variables locales en cas d'erreur
```bash
./venv/Scripts/pytest tests/unit/ -l
```

### Capture stdout/stderr
```bash
./venv/Scripts/pytest tests/unit/ -s
```

### Lister les tests sans les exécuter
```bash
./venv/Scripts/pytest tests/unit/ --collect-only
./venv/Scripts/pytest tests/unit/ -q --collect-only
```

### Marquer des tests comme xfail (expected to fail)
```bash
./venv/Scripts/pytest tests/unit/ -v -r xfE
```

---

## ⏱️ PERFORMANCE

### Mesurer le temps par test
```bash
./venv/Scripts/pytest tests/unit/ -v --durations=10
```

### Les 10 tests les plus lents
```bash
./venv/Scripts/pytest tests/unit/ --durations=10
```

### Les 5 tests les plus rapides
```bash
./venv/Scripts/pytest tests/unit/ --durations=5 --durations-min=0
```

### Temps total d'exécution
```bash
# Voir en fin du rapport pytest
./venv/Scripts/pytest tests/unit/ -v | Select-Object -Last 5
```

---

## 🎯 FILTRAGE AVANCÉ

### Par nom de test (regex)
```bash
# Tous les tests contenant "JWT"
./venv/Scripts/pytest tests/unit/ -k "JWT" -v

# Tous les tests sauf ceux contenant "TOTP"
./venv/Scripts/pytest tests/unit/ -k "not TOTP" -v

# JWT ou AES
./venv/Scripts/pytest tests/unit/ -k "JWT or AES" -v

# Password mais pas Hash
./venv/Scripts/pytest tests/unit/ -k "Password and not Hash" -v
```

### Par marqueur (marker)
```bash
./venv/Scripts/pytest tests/unit/ -m "slow" -v
./venv/Scripts/pytest tests/unit/ -m "not slow" -v
```

### Tests échoués précédents
```bash
./venv/Scripts/pytest tests/unit/ --lf  # last failed
./venv/Scripts/pytest tests/unit/ --ff  # failed first
```

---

## 📝 CONFIGURATION PYTEST

### Fichier `pytest.ini` (optionnel)
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --strict-markers --tb=short
markers =
    slow: tests qui sont lents à exécuter
    security: tests de sécurité
    crypto: tests cryptographiques
```

### Utiliser le fichier config
```bash
./venv/Scripts/pytest tests/unit/ --ini=pytest.ini
```

---

## 🔗 INTÉGRATION CI/CD

### GitHub Actions (exemple)
```yaml
name: Unit Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      - run: pip install -r requirements.txt
      - run: pytest tests/unit/ -v --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v2
```

### GitLab CI (exemple)
```yaml
test:
  image: python:3.13
  script:
    - pip install -r requirements.txt
    - pytest tests/unit/ -v --cov=app
  coverage: '/TOTAL.*\s+(\d+%)$/'
```

### Jenkins (exemple)
```groovy
stage('Test') {
    steps {
        sh 'pip install -r requirements.txt'
        sh 'pytest tests/unit/ -v --junit-xml=results.xml'
        junit 'results.xml'
    }
}
```

---

## 🧬 STRUCTURE DES TESTS

### Où ajouter de nouveaux tests?

**Pour tester un module app/core/xxx.py**:
```
tests/unit/test_xxx.py
```

**Template minimal**:
```python
import pytest
from app.core.xxx import function_to_test

class TestMyFeature:
    """Tests pour ma fonctionnalité."""
    
    def test_case_1(self):
        """Description du test."""
        result = function_to_test("input")
        assert result == "expected"
    
    def test_case_2(self):
        """Description du test."""
        with pytest.raises(ValueError):
            function_to_test("invalid")
```

### Dossiers de tests
```
tests/
├── unit/              # Tests unitaires (69 tests)
├── integration/       # Tests d'intégration (optionnel)
├── fixtures/          # Données de test
└── conftest.py        # Configuration globale
```

---

## 🛠️ MAINTENANCE

### Nettoyer les caches
```bash
# Supprimer .pytest_cache
rm -r tests/.pytest_cache
rm -r .pytest_cache

# Supprimer __pycache__
rm -r tests/__pycache__
rm -r app/__pycache__

# Supprimer rapports HTML
rm -r htmlcov/
```

### Mettre à jour pytest
```bash
./venv/Scripts/pip install --upgrade pytest
./venv/Scripts/pip install --upgrade pytest-cov
./venv/Scripts/pip install --upgrade pytest-asyncio
```

### Vérifier les versions
```bash
./venv/Scripts/pytest --version
./venv/Scripts/pip list | grep pytest
```

---

## ❓ DÉPANNAGE

### Erreur: "No tests collected"
```bash
# Vérifier la structure
./venv/Scripts/pytest tests/unit/ --collect-only

# Vérifier les fichiers commencent par test_
ls tests/unit/
```

### Erreur: "ModuleNotFoundError"
```bash
# Vérifier l'installation des packages
./venv/Scripts/pip install -r requirements.txt

# Vérifier PYTHONPATH
$env:PYTHONPATH = "$PWD"
```

### Tests lents
```bash
# Lister les tests lents
./venv/Scripts/pytest tests/unit/ --durations=20

# Exécuter en parallèle
./venv/Scripts/pip install pytest-xdist
./venv/Scripts/pytest tests/unit/ -n auto
```

### Warnings excessifs
```bash
# Ignorer les warnings
./venv/Scripts/pytest tests/unit/ -W ignore

# Filtrer par type
./venv/Scripts/pytest tests/unit/ -W ignore::DeprecationWarning
```

---

## 📚 RESSOURCES

### Documentation Officielle
- [pytest Documentation](https://docs.pytest.org/)
- [pytest Plugins](https://docs.pytest.org/en/latest/reference.html)
- [unittest vs pytest](https://docs.pytest.org/en/latest/how-to-assert.html)

### Plugins Recommandés
```bash
pip install pytest-cov          # Coverage reports
pip install pytest-xdist        # Parallel execution
pip install pytest-timeout      # Test timeouts
pip install pytest-mock         # Mocking utilities
pip install pytest-asyncio      # Async support
```

### Best Practices
1. ✅ Un test = une responsabilité
2. ✅ Noms de tests clairs et descriptifs
3. ✅ Arrange → Act → Assert pattern
4. ✅ Eviter les dépendances entre tests
5. ✅ Utiliser les fixtures pour le setup/teardown

---

## 🎓 EXEMPLE COMPLET

### Script complet d'exécution
```bash
#!/bin/bash
set -e

echo "🧪 Exécution des tests BARROW.AI..."
echo ""

# Configuration
cd barrow-ai-backend
source ./venv/Scripts/activate

# Nettoyage
echo "🧹 Nettoyage des caches..."
rm -rf .pytest_cache __pycache__ htmlcov/

# Exécution
echo "🚀 Lancement des tests..."
./venv/Scripts/pytest tests/unit/ \
    --ignore=tests/unit/test_output_validator.py \
    -v \
    --tb=short \
    --cov=app \
    --cov-report=html \
    --cov-report=term-missing

echo ""
echo "✅ Tests terminés!"
echo "📊 Rapport HTML: htmlcov/index.html"
```

---

## 📞 SUPPORT

- **Questions**: Consultez `RAPPORT_TESTS_UNITAIRES.md`
- **Modifications**: Voir `RESUME_MODIFICATIONS_TECHNIQUES.md`
- **Structure**: Voir `.env.example` et `conftest.py`

---

*Version: 1.0 - April 24, 2026*
*BARROW.AI Backend Testing Suite*

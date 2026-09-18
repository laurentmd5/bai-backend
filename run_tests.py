#!/usr/bin/env python3
"""
Script pour exécuter la suite de tests complète du backend BARROW.AI.
Usage: python run_tests.py [options]
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Exécute une commande et affiche le résultat."""
    print(f"\n{'='*60}")
    print(f"📋 {description}")
    print(f"{'='*60}")
    print(f"Commande: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n❌ Exécution interrompue par l'utilisateur")
        return False
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Exécute la suite de tests du backend BARROW.AI"
    )
    parser.add_argument(
        "--type",
        choices=["all", "unit", "integration", "security", "performance"],
        default="all",
        help="Type de tests à exécuter"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Générer un rapport de couverture"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Sortie verbose"
    )
    parser.add_argument(
        "--failfast",
        "-x",
        action="store_true",
        help="S'arrêter au premier test échoué"
    )
    parser.add_argument(
        "--parallel",
        "-n",
        action="store_true",
        help="Exécuter les tests en parallèle"
    )
    parser.add_argument(
        "--markers",
        "-m",
        help="Exécuter les tests avec un marker spécifique"
    )
    
    args = parser.parse_args()
    
    # Construction de la commande de base
    base_cmd = ["python", "-m", "pytest"]
    
    # Ajouter les options
    if args.verbose:
        base_cmd.append("-vv")
    else:
        base_cmd.append("-v")
    
    if args.failfast:
        base_cmd.append("-x")
    
    if args.parallel:
        base_cmd.extend(["-n", "auto"])
    
    if args.coverage:
        base_cmd.extend([
            "--cov=app",
            "--cov-report=html",
            "--cov-report=term-missing",
        ])
    
    if args.markers:
        base_cmd.extend(["-m", args.markers])
    
    # Ajouter les chemins de test
    if args.type == "all":
        base_cmd.append("tests/")
    elif args.type == "unit":
        base_cmd.append("tests/unit/")
    elif args.type == "integration":
        base_cmd.append("tests/integration/")
    elif args.type == "security":
        base_cmd.extend(["-m", "security"])
    elif args.type == "performance":
        base_cmd.extend(["-m", "performance"])
    
    # Exécuter les tests
    success = run_command(base_cmd, f"Exécution des tests ({args.type})")
    
    if success:
        print(f"\n✅ Tous les tests ont réussi!")
        if args.coverage:
            print("\n📊 Rapport de couverture généré: htmlcov/index.html")
    else:
        print(f"\n❌ Certains tests ont échoué")
        sys.exit(1)


if __name__ == "__main__":
    main()

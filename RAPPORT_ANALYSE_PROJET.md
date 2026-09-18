# Rapport d'analyse du projet BARROW.AI Backend

**Date:** 28 août 2026  
**Périmètre:** code Python, configuration, Docker Compose, documentation et tests présents dans le dépôt  
**Méthode:** lecture ciblée des composants structurants, recherche de marqueurs de risque et contrôles locaux de syntaxe et de collecte pytest

## 1. Résumé exécutif

BARROW.AI Backend est une plateforme FastAPI de chatbot multi-entreprise fondée sur un pipeline RAG. Le projet assemble une API REST, une interface d'administration, un canal WhatsApp, PostgreSQL, Redis, Qdrant, RabbitMQ, des fournisseurs LLM et des services audio.

L'architecture est ambitieuse et globalement bien séparée: routes, services, repositories, modèles, middleware et migrations sont identifiables. Les contrôles de sécurité annoncés sont également présents dans le code: JWT, Argon2id, TOTP, CSRF, validation des entrées, limitation de débit et en-têtes de sécurité.

**Verdict:** base technique exploitable, mais non suffisamment vérifiée pour conclure à un état production-ready. Le principal risque immédiat est la validation insuffisante de l'environnement de test. Plusieurs points de déploiement et de documentation doivent aussi être corrigés avant une mise en production durable.

## 2. Constats principaux

| Priorité | Constat | Impact | Action recommandée |
|---|---|---|---|
| Haute | La collecte pytest échoue avec `ModuleNotFoundError: pyotp` | Aucun test ne peut démarrer dans l'interpréteur contrôlé | Installer `requirements.txt`/`requirements-test.txt` dans l'interpréteur utilisé, puis exécuter la suite complète |
| Haute | En production, `/openapi.json` est désactivé mais `/docs` et `/redoc` sont ajoutés avec cette URL | Documentation interactive probablement inutilisable | Soit conserver une route OpenAPI protégée, soit désactiver aussi les routes docs |
| Haute | Uvicorn utilise `--forwarded-allow-ips *` | Des en-têtes proxy peuvent être considérés comme fiables depuis n'importe quelle source | Limiter aux proxies connus et vérifier la configuration Traefik |
| Moyenne | La readiness ne vérifie que PostgreSQL et Redis | Le pod peut être déclaré prêt alors que Qdrant ou le LLM sont indisponibles | Définir les dépendances nécessaires et inclure leurs checks dans `/health/ready` |
| Moyenne | Plusieurs images Docker utilisent `latest` | Déploiements non reproductibles et mises à jour imprévisibles | Épingler des versions ou des digests |
| Moyenne | Documentation et configuration ne sont pas parfaitement alignées | Risque de mauvais dimensionnement ou de mauvaise configuration | Faire de la configuration réelle la source de vérité et supprimer les valeurs obsolètes |

## 3. Architecture observée

Le point d'entrée est [`app/main.py`](app/main.py). L'application configure FastAPI, CORS, six middlewares principaux, les routeurs API et l'interface admin. Le cycle de vie initialise la base, Redis, les providers LLM/embeddings, le service RAG et RabbitMQ.

Les responsabilités principales sont réparties ainsi:

- **API:** chat, feedback, WhatsApp, santé et administration dans `app/api/`.
- **Services:** orchestration conversationnelle, RAG, LLM, audio, cache, file de messages et validation dans `app/services/`.
- **Persistance:** SQLAlchemy asynchrone et repositories dans `app/models/`, `app/repositories/` et `app/core/database.py`.
- **Infrastructure:** PostgreSQL, Redis, Qdrant, RabbitMQ, Ollama, Prometheus et Grafana dans [`docker-compose.yml`](docker-compose.yml).
- **Configuration:** variables d'environnement validées par Pydantic dans [`app/core/config.py`](app/core/config.py), identité métier dans [`company.yaml`](company.yaml).

Le choix d'un provider local d'embeddings et le chargement anticipé du modèle dans le Dockerfile peuvent réduire la latence au démarrage, mais augmentent fortement la taille de l'image et les besoins mémoire.

## 4. Sécurité

### Points positifs

- Mots de passe hashés avec Argon2id dans [`app/core/security.py`](app/core/security.py).
- JWT avec expiration, type, `jti`, `iat` et `nbf`.
- Clé AES-256 validée par décodage Base64 au démarrage.
- TOTP et codes de récupération prévus pour l'administration.
- Middleware CSRF, rate limiting, CORS et en-têtes de sécurité présents.
- Le Dockerfile exécute l'application avec un utilisateur non privilégié.
- Les logs disposent d'une liste de champs sensibles à masquer dans [`app/core/logging.py`](app/core/logging.py).

### Risques à traiter

1. **Confiance proxy trop large.** [`Dockerfile`](Dockerfile) passe `--forwarded-allow-ips *`. Cette option doit être limitée aux reverse proxies réellement utilisés; elle est particulièrement sensible pour les contrôles basés sur l'adresse IP et les logs.
2. **Exposition d'outils d'infrastructure.** [`docker-compose.yml`](docker-compose.yml) expose RabbitMQ sur les ports 5672 et 15672. Ces ports ne devraient pas être publiés sur un hôte accessible sans filtrage réseau strict.
3. **Whitelist réseau permissive par défaut.** La valeur par défaut de `ADMIN_IP_WHITELIST` inclut tout le sous-réseau Docker `172.20.0.0/16`. En production, cette valeur doit être explicitement fournie et testée.
4. **Documentation Swagger en production.** Le schéma OpenAPI est désactivé en production, mais les endpoints `/docs` et `/redoc` sont tout de même enregistrés avec `/openapi.json`. Il faut choisir un comportement cohérent et, si la documentation est conservée, l'authentifier.

## 5. Fiabilité et exploitation

Le démarrage tolère l'indisponibilité de Redis, RabbitMQ et des providers LLM en continuant en mode dégradé. C'est utile pour certains scénarios, mais le contrat d'exploitation doit être explicite: une application qui répond avec des fallbacks ne doit pas être confondue avec une application pleinement opérationnelle.

Le endpoint `/health/ready` ne vérifie actuellement que PostgreSQL et Redis, tandis que `/health` vérifie aussi le LLM, Qdrant et le cache. Il existe donc un écart entre l'état “ready” et la capacité réelle à traiter une requête RAG.

Les images `qdrant/qdrant:latest`, `ollama/ollama:latest`, Prometheus et Grafana non épinglées rendent les builds et les restaurations moins déterministes. Les migrations Alembic et les volumes persistants sont présents, ce qui constitue une bonne base, mais les migrations doivent être exécutées et vérifiées dans le pipeline de déploiement.

## 6. Cohérence technique et documentation

Quelques divergences ont été observées:

- [`README.md`](README.md) annonce Gemini avec fallback Groq, tandis que `LLMProvider` ne permet de sélectionner directement que Gemini ou Ollama. Groq est utilisé comme fallback dans certains chemins de service, mais n'est pas un provider sélectionnable par configuration.
- Le README mentionne `intfloat/multilingual-e5-large`; la documentation d'architecture mentionne aussi BGE en 384 dimensions, alors que `QDRANT_VECTOR_SIZE` vaut 1024 et que le provider local est chargé par le code. Le modèle et la dimension effective doivent être documentés en un seul endroit.
- Les documents de tests annoncent plus de 420 tests et une couverture estimée à 85%+, mais cette couverture n'a pas pu être confirmée dans l'environnement courant, car pytest ne passe pas la phase d'import.
- Le dépôt contient de nombreux rapports historiques. Ils sont utiles pour la traçabilité, mais leurs dates, chiffres et conclusions doivent être identifiés comme historiques pour éviter de les prendre pour un état actuel.

## 7. Tests et qualité

### Contrôles exécutés

- `python -m compileall -q app tests`: **réussi**, aucune erreur de syntaxe détectée.
- `python -m pytest --collect-only -q`: **échec avant collecte**, `tests/conftest.py` importe `pyotp`, absent de l'interpréteur courant.

Le problème peut être uniquement lié à l'environnement local: `pyotp` est bien déclaré dans [`requirements.txt`](requirements.txt). Il reste toutefois bloquant pour la reproductibilité tant que le projet ne fournit pas un chemin d'installation vérifié et un interpréteur explicitement sélectionné.

### Suite recommandée

1. Installer les dépendances avec l'interpréteur réellement utilisé par VS Code.
2. Rejouer `pytest --collect-only -q`.
3. Exécuter les tests unitaires, puis les tests d'intégration et de sécurité séparément.
4. Produire la couverture avec `pytest --cov=app --cov-report=term-missing`.
5. Ajouter au CI un échec explicite sous le seuil de couverture retenu; actuellement le seuil est commenté dans [`pytest.ini`](pytest.ini).

## 8. Plan d'action priorisé

### Immédiat

- Réparer l'environnement de test et publier la commande d'installation validée.
- Corriger le couple `/docs`/`/openapi.json` en production.
- Restreindre `--forwarded-allow-ips` et ne pas publier RabbitMQ sans protection réseau.

### Court terme

- Étendre la readiness à Qdrant et au provider LLM, ou documenter clairement le mode dégradé.
- Épingler toutes les images et dépendances critiques de production.
- Centraliser les paramètres du modèle d'embeddings, sa dimension et la collection Qdrant.
- Activer le seuil de couverture CI après avoir obtenu une mesure réelle.

### Moyen terme

- Réduire les rapports historiques redondants ou les indexer par date et statut.
- Ajouter des tests de démarrage, de readiness dégradée et de documentation OpenAPI en environnement production.
- Tester les limites de sécurité derrière le reverse proxy réel, notamment l'IP client, CSRF et rate limiting.

## 9. Conclusion

Le projet dispose d'une base modulaire et de nombreux mécanismes nécessaires à un service IA exploitable. La prochaine étape n'est pas d'ajouter davantage de fonctionnalités, mais de fermer l'écart entre les garanties documentées et les garanties démontrées: environnement de test reproductible, checks de disponibilité cohérents, configuration de déploiement déterministe et documentation alignée sur le code.
# Rapport d'audit complet du projet BARROW.AI

**Date de l'audit :** 2026-09-18  
**Périmètre :** application FastAPI, authentification/RBAC, API publiques et admin, WhatsApp, RAG/LLM, persistance, workers, middleware, Docker/Compose, CI/CD, dépendances et tests présents dans le dépôt.  
**Méthode :** lecture ciblée des chemins d'exécution, analyse de configuration et déploiement, recherche de secrets/valeurs dangereuses, compilation Python et tentative de collecte pytest. Les anciens rapports du dépôt ont été utilisés comme contexte historique, pas comme preuves de l'état actuel.

## 1. Conclusion exécutive

Le projet possède une base technique sérieuse : séparation API/services/repositories, Argon2id, JWT avec expiration et `jti`, TOTP, CSRF pour les requêtes navigateur, validation de noms de fichiers, logs structurés, conteneur non-root et tests nombreux sur le papier.

Cependant, l'état actuel ne doit pas être considéré comme prêt pour une exposition Internet sans remédiation. Les faiblesses les plus préoccupantes sont :

1. **Création d'un compte superadmin avec mot de passe connu dans le pipeline CI/CD.**
2. **Secret interservices connu par défaut et utilisé comme seul contrôle d'accès à l'endpoint interne WhatsApp.**
3. **Signature WhatsApp non obligatoire : un webhook sans signature est accepté puis traité.**
4. **Rate limiting et certains contrôles de session qui échouent en mode permissif lors d'une panne Redis.**
5. **Confiance proxy globale et publication directe du backend sur le port 8000.**
6. **Qdrant sans authentification/TLS dans Compose, avec données sensibles potentiellement accessibles depuis le réseau interne.**
7. **Dépendances et images `latest`, absence de vérification reproductible des vulnérabilités.**
8. **Tests non exécutables dans l'interpréteur actif et seuil de couverture non bloquant.**

**Niveau global estimé : élevé.** La présence de contrôles ne compense pas ces contournements : plusieurs défenses critiques dépendent d'une configuration externe correcte ou autorisent explicitement le fonctionnement sans elles.

## 2. Résumé des constats

| ID | Sévérité | Domaine | Constat | Impact principal |
|---|---|---|---|---|
| C-01 | Critique | CI/CD / identité | Mot de passe superadmin codé en clair et affiché dans Jenkins | Compromission immédiate de l'administration |
| C-02 | Critique | Interservices | Secret interne par défaut, statique, contrôle unique | Injection de tâches WhatsApp et consommation LLM |
| C-03 | Critique | Webhook | Signature HMAC seulement vérifiée si elle est fournie | Requêtes forgées traitées sans preuve d'origine |
| C-04 | Haute | Disponibilité | Rate limiting `fail open` si Redis est indisponible | DoS, brute force et coûts LLM sans limite |
| C-05 | Haute | Proxy / réseau | `--forwarded-allow-ips *` et backend publié sur `0.0.0.0:8000` | Usurpation IP, bypass de limites, exposition directe |
| C-06 | Haute | Données | Qdrant sans clé API/TLS et endpoints infra peu cloisonnés | Lecture, altération ou exfiltration de la base vectorielle |
| C-07 | Haute | IA / RAG | Documents administrateur injectés dans le contexte LLM sans frontière de confiance démontrée | Prompt injection indirecte, divulgation ou actions non prévues |
| C-08 | Haute | Fichiers / ressources | Upload lu entièrement en mémoire, parsing CPU/ZIP/PDF sans budget global | Épuisement mémoire/CPU et instabilité |
| C-09 | Haute | Sécurité opérationnelle | Images `latest`, dépendances flottantes et pas de scan bloquant | Supply-chain et déploiements non déterministes |
| C-10 | Haute | Secrets / logs | Journaux et réponses d'erreur risquent d'exposer des données internes/PII | Fuite de secrets, PII et détails d'implémentation |
| C-11 | Moyenne | Auth/RBAC | Autorisations basées en partie sur les claims JWT et validations insuffisamment centralisées | Accès prolongé après changement de rôle/désactivation |
| C-12 | Moyenne | Files d'attente | Absence de DLQ et erreurs RabbitMQ ack/discard | Perte silencieuse de messages WhatsApp |
| C-13 | Moyenne | État / conformité | Données conversationnelles et numéros WhatsApp conservés sans politique visible de rétention/minimisation | Risque RGPD/confidentialité et coût de stockage |
| C-14 | Haute | Qualité | Tests bloqués avant collecte, couverture non imposée, tests parfois tolérants | Régressions de sécurité non détectées |
| C-15 | Moyenne | Documentation | Rapports historiques contradictoires avec le code courant | Mauvaises décisions d'exploitation et faux sentiment de sécurité |

## 3. Faiblesses critiques et hautes

### C-01 - Mot de passe superadmin exposé dans le pipeline CI/CD

**Preuve :** `Jenkinsfile`, `Jenkinsfile.local` et `Jenkinsfile.preprod` utilisent `--password Admin123!` et impriment aussi les identifiants dans le message de succès.

**Impact :** toute personne ayant accès au dépôt, aux logs Jenkins, à un artefact de pipeline ou à une image de log peut tenter la connexion superadmin. Le compte est créé automatiquement si la table est vide. Le mot de passe est également réutilisé dans les données de test et les scripts de seed.

**Remédiation immédiate :** supprimer le secret du dépôt et de tous les logs; injecter un secret Jenkins/Vault au runtime; forcer une rotation; créer un compte bootstrap à usage unique; exiger le changement de mot de passe et 2FA avant activation; ne jamais afficher le mot de passe dans `post { success }`.

### C-02 - Secret interservices connu par défaut

**Preuve :** `app/core/config.py` fournit `internal-secret-token-for-worker-delegation` par défaut; `docker-compose.yml` le réutilise si `INTERNAL_API_SECRET` est absent. `app/api/v1/endpoints/internal.py` protège `/api/v1/internal/process-whatsapp` uniquement par comparaison de ce secret.

**Impact :** un attaquant capable d'atteindre le backend ou un service du réseau Docker peut forger une tâche WhatsApp et déclencher traitements LLM, audio, écritures en base et envois sortants. Le secret n'est pas lié à l'identité du worker, n'a pas de rotation visible et n'est pas limité par réseau/mTLS.

**Remédiation :** rendre ce paramètre obligatoire en production et refuser tout secret correspondant à une valeur connue; utiliser mTLS ou un jeton signé avec audience, expiration et nonce; limiter l'endpoint au réseau worker; ajouter anti-rejeu et rate limit dédié; comparer en temps constant; journaliser l'identité du service sans le secret.

### C-03 - Webhooks WhatsApp acceptés sans signature

**Preuve :** dans `app/services/whatsapp_service.py`, `process_webhook()` ne rejette la requête que si `signature` est présente et invalide : `if signature and not self._validate_signature(...)`. Dans `app/api/v1/endpoints/whatsapp.py`, la signature est optionnelle et le webhook est publié dans RabbitMQ même lorsqu'elle est absente. Le même comportement existe via l'endpoint interne.

**Impact :** n'importe quel client pouvant atteindre le webhook peut produire un payload valide et faire traiter un message forgé. Cela peut générer des réponses, des coûts LLM, du spam sortant et des enregistrements contaminés.

**Remédiation :** en production, absence de `X-Hub-Signature-256` = rejet; valider HMAC sur les octets bruts avant parse et avant mise en file; vérifier l'`app_secret` configuré; ajouter un test d'acceptation/refus; ne pas loguer le payload brut.

### C-04 - Rate limiting permissif en panne Redis

**Preuve :** `app/services/validation/security_validator.py` retourne `True` lorsque Redis échoue. Le verrouillage login dans `app/api/v1/endpoints/admin/auth.py` documente et implémente également un fonctionnement `fail open`. Les compteurs IP/session et les contrôles de blacklist ne sont donc plus effectifs pendant une panne.

**Impact :** brute force d'administration, saturation du service, appels LLM coûteux et contournement des protections précisément lors d'un incident. Une panne Redis peut aussi affecter les sessions et la révocation.

**Remédiation :** distinguer les contrôles obligatoires des optimisations; utiliser un limiteur local borné en secours pour login/webhook/chat; pour les opérations d'administration, refuser ou dégrader explicitement; faire apparaître cet état dans readiness/alerting; tester le comportement sous panne.

### C-05 - Confiance proxy globale et exposition directe du backend

**Preuve :** `Dockerfile` lance Uvicorn avec `--forwarded-allow-ips *`; `docker-compose.yml` publie `8000:8000`. Le rate limiter tente de protéger `X-Forwarded-For`, mais Uvicorn peut déjà avoir réécrit les informations client à partir d'un proxy non fiable.

**Impact :** usurpation d'adresse IP dans les logs et protections IP, bypass du rate limiting, fausses traces d'audit et difficulté d'investigation. L'exposition du backend contourne les règles TLS, WAF et filtrage du reverse proxy.

**Remédiation :** ne pas publier le port backend en production ou le lier à localhost/réseau privé; limiter `forwarded-allow-ips` aux adresses exactes du reverse proxy; définir une stratégie unique de résolution IP; tester avec chaînes `X-Forwarded-For` forgées.

### C-06 - Qdrant sans authentification ni chiffrement

**Preuve :** `docker-compose.yml` démarre Qdrant sur le réseau Docker sans `QDRANT__SERVICE__API_KEY`, TLS ou règle de réseau dédiée. `qdrant_url` utilise `http://`.

**Impact :** un service compromis sur le réseau peut lire ou modifier les embeddings et leurs payloads, supprimer une collection ou empoisonner la base de connaissance. Les payloads peuvent contenir des extraits de documents confidentiels.

**Remédiation :** activer une API key/mTLS, TLS, réseau isolé et politique firewall; ne jamais exposer Qdrant à l'hôte; limiter les permissions du client applicatif; chiffrer les sauvegardes et vérifier la restauration.

### C-07 - Risque d'injection indirecte dans le RAG

**Preuve :** les documents uploadés sont indexés puis intégrés au pipeline RAG; `RAGService` fusionne recherche vectorielle et recherche lexicale. La validation de prompt est appliquée au message utilisateur, mais aucune frontière de confiance explicite n'est démontrée pour le texte récupéré avant son insertion dans le prompt LLM. La validation de pertinence dans `ChatService._is_response_relevant()` retourne `True` avant le contrôle de score dans le chemin observé.

**Impact :** un document malveillant ou compromis peut contenir des instructions qui manipulent le modèle, provoquent une divulgation de contexte ou changent le comportement du bot. Le score de confiance peut être artificiellement relevé lorsqu'un résultat lexical existe.

**Remédiation :** délimiter et étiqueter les sources comme données non fiables; utiliser un prompt système qui interdit de suivre les instructions des documents; filtrer les documents par provenance/publication; vérifier le score réel avant tout boost lexical; ajouter tests d'injection indirecte et de fuite de contexte.

### C-08 - Épuisement de ressources sur uploads et parsing

**Preuve :** `app/api/v1/endpoints/admin/knowledge.py` appelle `await file.read()` avant de vérifier la taille. Le parsing PDF/DOCX de `app/services/admin/document_parser.py` peut parcourir de nombreuses pages/structures et le document est ensuite découpé et envoyé à une tâche de fond. Les fichiers WhatsApp audio/document suivent également des chemins de téléchargement et conversion lourds.

**Impact :** un fichier supérieur à la limite est déjà entièrement chargé avant rejet; des fichiers compressés, PDFs complexes ou lots de messages peuvent saturer RAM/CPU, bloquer l'event loop et retarder l'administration.

**Remédiation :** imposer la taille au niveau reverse proxy et serveur; lire par chunks avec compteur et abandon; borner pages, texte extrait, profondeur/temps CPU et nombre de chunks; isoler le parsing dans un worker avec quotas; nettoyer systématiquement les temporaires; ajouter limites par administrateur et par expéditeur.

### C-09 - Supply-chain et déploiements non reproductibles

**Preuve :** Compose utilise `qdrant/qdrant:latest`, `ollama/ollama:latest`, Prometheus/Grafana `latest`; `requirements.txt` contient aussi `>=` pour plusieurs dépendances. Le pipeline pousse et redéploie un tag `latest`; aucun scan SCA/SBOM bloquant n'a été identifié dans les Jenkinsfiles.

**Impact :** une mise à jour amont peut modifier le comportement, introduire une vulnérabilité ou casser les migrations sans changement du dépôt. Les restaurations ne garantissent pas le même binaire.

**Remédiation :** épingler versions et digests; générer SBOM; scanner OS/Python/images à chaque build; signer/vérifier les images; promouvoir une image immuable par digest; appliquer une procédure de mise à jour et rollback.

### C-10 - Risques de fuite par logs et erreurs

**Preuve :** `internal.py` renvoie `detail=f"Internal processing failed: {str(e)}"`; plusieurs chemins loguent des erreurs fournisseurs et des métadonnées opérationnelles. Les endpoints de réponse exposent notamment `content_hash`, uploader et métadonnées de documents. La protection des logs est déclarée mais doit être vérifiée pour chaque logger et nouveau champ.

**Impact :** stack details, URLs, identifiants fournisseurs, noms de fichiers, contenus ou PII peuvent atteindre le client, Jenkins, Docker logs ou Prometheus. Les messages WhatsApp et conversations contiennent des données personnelles et potentiellement des CV.

**Remédiation :** erreurs externes génériques avec `request_id`; détails uniquement côté logs protégés; tests de non-divulgation; classification des champs; masquage centralisé des numéros, tokens, emails et noms de fichiers; rotation/chiffrement/TTL des logs.

## 4. Faiblesses moyennes et structurelles

### C-11 - Cycle de vie des privilèges insuffisamment durci

`get_current_admin()` reconstruit le rôle depuis le JWT après validation de session. Si le rôle ou l'état actif change en base, il faut démontrer que `validate_session()` revalide systématiquement ces attributs et invalide toutes les sessions. Sinon un token encore valide peut conserver un privilège supprimé jusqu'à son expiration. Les dépendances `require_admin`/`require_superadmin` sont bonnes comme intention, mais leur application à chaque mutation doit être vérifiée par route.

**Action :** charger l'utilisateur actif depuis la base à chaque opération sensible ou versionner les privilèges; invalider sessions/tokens sur changement de rôle, désactivation et changement de mot de passe; matrice RBAC automatisée par endpoint.

### C-12 - Perte de messages RabbitMQ

`rabbitmq_service.py` utilise `message.process()` et indique qu'une exception sera ack/discard. Aucun dead-letter exchange, retry borné, idempotence durable ou file d'échec n'est visible. L'idempotence WhatsApp est en cache Redis avec TTL d'une heure, donc un redelivery tardif peut être retraité.

**Action :** nack/requeue selon classe d'erreur, DLQ, backoff, clé d'idempotence en base avec contrainte unique, métriques et alerte sur les échecs.

### C-13 - Conservation et minimisation des données

Les conversations stockent le message utilisateur, réponse, sources, métadonnées et informations de session; WhatsApp utilise le numéro de téléphone comme identifiant externe. Une politique de rétention, suppression utilisateur, anonymisation et export n'est pas apparente dans le périmètre inspecté.

**Action :** définir durée par type de donnée, chiffrement applicatif réellement appliqué aux colonnes sensibles, purge planifiée, accès d'audit et procédure de demande de suppression.

### C-14 - Qualité et tests non fiables au moment de l'audit

`python -m compileall -q app tests` réussit. En revanche `python -m pytest --collect-only -q` échoue avant collecte avec `ModuleNotFoundError: No module named 'pyotp'` dans `tests/conftest.py`. Le dépôt annonce plus de 420 tests, mais cette suite n'est pas exécutable dans l'interpréteur courant. Les tests tolèrent parfois plusieurs statuts (`in [200, 201]`, `in [200, 503]`) et le seuil de couverture n'est pas une barrière de CI visible.

**Action :** verrouiller l'interpréteur et installer `requirements-test.txt`; lancer collecte puis unitaires/intégration/security séparément; publier coverage réelle; rendre le seuil bloquant; ajouter tests négatifs pour absence de signature WhatsApp, secret par défaut, panne Redis, proxy forgé, privilège après révocation et DLQ.

### C-15 - Documentation historique contradictoire

Plusieurs rapports affirment que des remédiations sont terminées alors que le code garde des valeurs par défaut dangereuses ou des contrôles permissifs. Les rapports annoncent aussi des chiffres de couverture non vérifiés dans l'environnement courant.

**Action :** marquer les rapports historiques, produire un seul état de référence daté, relier chaque contrôle à un test CI et supprimer les affirmations non démontrées.

## 5. Points positifs à préserver

- Argon2id avec sel aléatoire pour les mots de passe.
- JWT avec `exp`, `iat`, `nbf`, `jti` et séparation access/refresh.
- TOTP et codes de secours prévus pour l'administration.
- Validation de type de fichier, extension, nom et hash de contenu côté upload.
- Middleware CSRF pour les méthodes mutantes non exemptées.
- En-têtes de sécurité et CSP présents, même si la CSP contient `unsafe-inline`/`unsafe-eval`.
- Exécution Docker sous utilisateur non root.
- Séparation du worker RabbitMQ et du traitement lourd backend.
- Indexes de base ajoutés par migration 004 pour plusieurs requêtes critiques.
- Masquage partiel des identifiants WhatsApp dans les logs.

## 6. Plan d'action priorisé

### P0 - avant toute exposition publique

1. Révoquer et remplacer le mot de passe `Admin123!`; supprimer toutes les occurrences et logs associés.
2. Rendre `INTERNAL_API_SECRET`, JWT, chiffrement, CSRF et mots de passe infrastructure obligatoires en production; refuser les valeurs connues.
3. Exiger la signature WhatsApp et valider les octets bruts avant mise en file.
4. Retirer l'exposition publique de `8000`, Qdrant, Redis, RabbitMQ, Prometheus et Grafana; limiter les réseaux.
5. Remplacer `--forwarded-allow-ips *` par les proxies réels.
6. Corriger les réponses d'erreur internes et les logs pour ne jamais renvoyer de détails d'exception.

### P1 - durcissement sous 1 à 2 semaines

1. Ajouter DLQ/retry/idempotence durable RabbitMQ.
2. Mettre en place un fallback de rate limit local et une politique fail-closed pour l'administration.
3. Ajouter quotas de lecture, parsing isolé et limites CPU/RAM pour tous les médias/documents.
4. Protéger Qdrant par API key/TLS et cloisonnement réseau.
5. Revalider utilisateur/rôle/état actif sur les actions sensibles et tester toute la matrice RBAC.
6. Ajouter garde-fous d'injection indirecte dans le RAG et tests de contamination documentaire.

### P2 - industrialisation sous 1 mois

1. Épingler images/dépendances par digest et produire SBOM + scan SCA.
2. Réparer l'environnement de tests et imposer couverture/quality gates dans Jenkins.
3. Définir rétention, suppression, anonymisation, sauvegardes chiffrées et exercices de restauration.
4. Unifier configuration, documentation active et rapports historiques.
5. Ajouter alertes sur secrets par défaut, erreurs Redis, DLQ, latence LLM et taux de rejet de signature.

## 7. Vérifications recommandées après correction

```text
- pytest --collect-only -q
- pytest tests/unit tests/integration/test_csrf.py tests/unit/test_worker_delegation.py -q
- pytest --cov=app --cov-report=term-missing --cov-fail-under=85
- bandit -r app worker.py
- pip-audit -r requirements.txt
- docker scout cves <image>@<digest>
- test webhook: signature absente, invalide, valide, corps modifié après signature
- test Redis indisponible: login, chat, admin, révocation et rate limiting
- test proxy: chaînes X-Forwarded-For forgées depuis une source non approuvée
- test RBAC: rôle modifié/désactivé après émission du JWT
- test upload: taille maximale, PDF/DOCX bomb, pages/chunks excessifs
- test RabbitMQ: erreur permanente, redelivery, DLQ et doublon
```

## 8. Limites de cet audit

L'audit est fondé sur le dépôt local au 2026-09-18. Aucun test d'intrusion réseau, test de production, scan complet des dépendances, inspection des secrets du gestionnaire CI, analyse de toutes les politiques Traefik ou vérification de la configuration réelle PostgreSQL/Redis/Qdrant n'a été possible depuis le workspace. Les constats marqués comme risques doivent être confirmés dans l'environnement déployé, mais les preuves de code/configuration suffisent pour traiter C-01 à C-06 comme des priorités immédiates.

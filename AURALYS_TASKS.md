# Auralys — Suivi des tâches (issu de l'audit)

Ce fichier suit l'état d'avancement des corrections identifiées lors de l'audit complet du projet. Il est organisé par priorité (urgent / important / futur), avec en tête les tâches de la session en cours.

Dernière mise à jour : 2026-07-07.

## Session — Reconnexion frontend/backend + authentification locale

**Contexte** : le frontend (Vue) appelait une API riche (`/health`, `/auth/*`, `/agent/chat`, `/conversations`, `/history`, `/admin/reviews*`, `/memories/active`, `/rag/status`, `/reference-values`, `/reference-browser`, endpoints audio) qui n'existait nulle part dans le backend réellement servi (`app/main.py` n'exposait que 4 routes `/api/auralys/*` de la stack mock) — d'où l'absence totale de communication frontend/backend signalée par l'utilisateur.

- [x] **`app/agent/store.py`** : bug d'indentation corrigé — `_build_conversation_title` déplacée après la classe, restaurant `save_memory`/`get_active_memory`/`save_action`/`list_pending_actions`/`update_action_status`/`save_tool_log` comme méthodes réelles de `AgentStore` (vérifié : elles n'existaient pas du tout sur la classe avant, `hasattr(...)` retournait `False`).
- [x] **`app/db/postgres.py::PostgresDatabase`** : ajout de `init_schema`, `upsert_conversation`, `insert_message`, `fetch_conversations`, `fetch_messages`, `insert_discussion_history`, `fetch_discussion_history`, `fetch_review_queue`, `upsert_review_case`, `insert_memory`, `fetch_active_memories` — toutes testées en round-trip contre le Postgres réel (`tests/test_agent_persistence.py`).
- [x] **Migration ponctuelle** : `agent_actions`/`agent_feedback` référençaient une table orpheline `agent_conversations` (dérive de schéma, présente en base mais absente de tout le code du dépôt) au lieu de `conversations(id)` comme prévu par `AgentStore.AGENT_SCHEMA_SQL`. FK corrigées par `ALTER TABLE ... DROP/ADD CONSTRAINT` (sans perte : 1 ligne dans `agent_actions`, 0 dans `agent_feedback`).
- [x] **Nouvelle couche API réelle** : `app/api/agent_routes.py` (toutes les routes attendues par le frontend, branchées sur `AppContainer` de `app/bootstrap.py`) + `app/api/__init__.py::create_app()` (CORS + dependency override pour les tests). `app/main.py` pointe maintenant vers cette vraie app (`app = app.api.create_app()`) au lieu de la stack mock — la stack mock reste dans le repo mais n'est plus servie par défaut.
- [x] **Authentification locale ajoutée** (à la demande explicite de l'utilisateur, en complément d'OAuth) : table `users` (Postgres, `password_hash` bcrypt), `app/auth/local_auth_service.py` (`create_user`/`authenticate`), route `POST /auth/login`, script `scripts/create_user.py` (création de compte via CLI interactif, pas d'inscription libre exposée en HTTP). Formulaire username/password restauré dans `LoginPage.vue` (+ boutons Google/Facebook toujours disponibles pour OAuth).
- [x] Vérifié en conditions réelles (navigateur piloté par Playwright) : page de login s'affiche, connexion avec un compte de test fonctionne, session persistée, conversation faite via `/agent/chat` apparaît bien dans `/conversations`/`/conversations/{key}/messages` (unification de la persistance des conversations confirmée de bout en bout).
- [x] Suite de tests complète : **54/54 passent** (`tests/test_agent_api.py` — les 2 échecs documentés plus bas sont réparés —, `tests/test_agent_persistence.py`, `tests/test_csv_intervention_loader.py`, et le reste).

### Point d'attention non résolu, à traiter avant toute exposition publique

Les routes de `app/api/agent_routes.py` ne vérifient **pas** le rôle/la session côté serveur : le frontend envoie `user_id`/`role` en clair dans le corps des requêtes (`/agent/chat`, etc.) et le backend leur fait confiance telles quelles. Il n'y a pas encore de session signée (cookie/JWT) ni de dépendance FastAPI qui bloque un `role=ceo` non légitime. Fonctionnel pour un usage interne de confiance, **pas acceptable si le backend est exposé au-delà du réseau interne** — voir la liste "Urgent" ci-dessous.

## Session — Ingestion de l'historique client (CSV)

**Objectif** : rendre ingérable un nouveau format d'export CSV d'historique d'intervention (`Aromair_01_2026_final.csv`, 227 lignes) dans le pipeline RAG réel (`app/ingestion` + `schemas/fiche_schema.py` + `schemas/chunk_schema.py`), pour que l'historique clientèle devienne interrogeable par le RAG agentic.

- [x] Fix critique : `EMBEDDING_DIMENSION` par défaut 1024 → 768 dans `app/config.py`, `.env`, `deploy/hostinger.env.example` (pour matcher la dimension native de `text-embedding-004`).
- [x] Sauvegarde des données fournies dans `data/raw_csv/Aromair_01_2026_final.csv` (nouveau dossier, format distinct des JSON OCR de `data/raw_json/`).
- [x] Nouveau module `app/ingestion/csv_intervention_loader.py` : parsing défensif (répare les lignes où l'adresse contient une virgule non échappée, ex. "Kantaoui, Sousse"), groupement par visite, construction de `FicheSchema`/`DiffuserControl`.
- [x] Branchement dans `app/ingestion/normalize.py` (`load_fiches_from_file`/`load_fiches_from_directory` gèrent maintenant `.csv`) — aucun changement requis dans `import_json_to_postgres.py` ni `index_qdrant.py` pour la lecture des fiches.
- [x] Tests unitaires `tests/test_csv_intervention_loader.py` (9 tests, fixture dédiée `data/test_fixtures/csv_interventions/`, isolée de `data/test_fixtures/pipeline/` pour ne pas perturber les assertions existantes).
- [x] Suite de tests complète relancée : aucune régression (seuls les 2 échecs déjà connus et documentés de `tests/test_agent_api.py` subsistent — preuve du split-brain architectural, non liés à ce travail).
- [x] Vérification sur le fichier réel complet (227 lignes → 154 visites, 460 chunks) : adresses "Kantaoui, Sousse" correctement reconstituées, textes de livraison mal placés dans `Nom_Parfum` corrigés vers les observations, aucune collision de `fiche_id`.

### Bug de données découvert et corrigé pendant l'implémentation

**`N_Fiche` n'est pas une clé unique fiable dans l'export réel.** La valeur `15949` est réutilisée pour deux visites totalement différentes (client, adresse et date différents — voir le fichier fourni). Un premier regroupement naïf par `N_Fiche` seul aurait silencieusement fusionné ces deux visites en une seule fiche, avec un risque concret d'écrasement en base (PK `fiche_id`) et de contamination des notes d'un client vers l'autre. **Corrigé** : le regroupement utilise désormais la clé composite `(N_Fiche, Client, Adresse, Date)`, et le `fiche_id` est désambiguïsé (`n_fiche_15949-1` / `n_fiche_15949-2`) quand un même `N_Fiche` correspond à plusieurs visites distinctes. Couvert par un test de non-régression dédié.

### Blocages découverts en tentant l'exécution de bout en bout (Postgres/Qdrant réels)

Docker a pu être démarré et les conteneurs `auralys-postgres`/`auralys-qdrant` sont opérationnels avec des données réelles préexistantes (451 fiches / 1925 chunks en Postgres, 3763 points dans la collection Qdrant `auralys_chunks`, en dimension 1024). Deux blocages **critiques et préexistants** (non liés à ce nouveau CSV) ont été découverts en essayant d'exécuter le pipeline réel jusqu'au bout — voir section "Nouveaux constats critiques" ci-dessous. En conséquence, **aucune écriture n'a été effectuée dans le Postgres/Qdrant réels** pour ne pas risquer de corrompre les données existantes : la vérification s'est arrêtée au niveau `FicheSchema`/`ChunkSchema` (Python pur, testé).

## Nouveaux constats critiques (découverts pendant cette session, à traiter en urgence)

1. **`app/ingestion/import_json_to_postgres.py` est actuellement du code mort — il ne peut pas s'exécuter.**
   `ingest_raw_json()` appelle `database.init_schema()`, `database.upsert_fiche(...)`, `database.upsert_chunk(...)`. Or `app/db/__init__.py` définit `Database = PostgresDatabase` et `default_database = PostgresDatabase()`, où `PostgresDatabase` (`app/db/postgres.py`) n'expose que `initialize_schema()`, `upsert_records()`, `fetch_records()`, `count_rows()` — et est branché sur `app.core.config.get_settings()` (la stack mock), pas sur le schéma `fiches`/`chunks` de `scripts/sql/001_init_core_schema.sql`. Aucune méthode `upsert_fiche`, `upsert_chunk` ou `init_schema` n'existe nulle part dans le code actuel (vérifié par recherche globale). **Conséquence : le pipeline d'ingestion réel vers Postgres est actuellement cassé pour tout le monde, pas seulement pour ce nouveau CSV.** Les 451 fiches/1925 chunks déjà présents en base ont dû être insérés par un autre moyen (script ponctuel, ancienne version du code, insertion manuelle) — l'origine exacte n'a pas été investiguée, hors périmètre de cette session.
   - **Action requise** : soit ajouter les méthodes manquantes à une classe `Database` correctement branchée sur `app.config.settings` et le schéma `fiches`/`chunks`, soit clarifier quelle classe est censée servir ce pipeline.

2. **L'appel Gemini réel échoue en 404 sur `text-embedding-004`.**
   Testé directement (sans toucher à Qdrant) : `EmbeddingService(backend="gemini", allow_fallback=False).embed_text(...)` lève `google.genai.errors.ClientError: 404 NOT_FOUND — models/text-embedding-004 is not found ... or is not supported for embedContent`. Ce n'est **pas** (uniquement) le bug de dimension déjà corrigé — le modèle lui-même semble inaccessible ou mal nommé pour cette clé API/version d'API. À investiguer : nom de modèle correct pour l'API actuellement utilisée (ex. `models/text-embedding-004` avec préfixe, ou migration vers `gemini-embedding-001`), et vérifier que la clé API a bien accès à l'API d'embeddings.
   - **Conséquence** : `index_qdrant.py` ne peut indexer aucun vecteur réel tant que ce point n'est pas résolu, quelle que soit la dimension configurée.

3. **La collection Qdrant `auralys_chunks` existante (3763 points, dim=1024) est incompatible avec le fix de dimension (768).**
   Une fois le point 2 résolu, réindexer avec la dimension corrigée nécessitera de recréer la collection (`recreate_collection`, déjà identifié comme destructif dans l'audit) — ce qui supprimera les 3763 points existants. **Ne pas exécuter sans confirmation explicite de l'utilisateur**, car on ne sait pas si ces points sont des embeddings réels exploitables ou déjà le résultat du fallback local (hash) — à vérifier avant de décider quoi migrer.

## Urgent avant toute mise en production

- [x] ~~Décider de la stack canonique et migrer `app/main.py`~~ — fait cette session (`app/main.py` sert maintenant la vraie app).
- [x] ~~Réparer `tests/test_agent_api.py`~~ — fait cette session (2/2 passent).
- [ ] **Nouveau, critique** : réparer le branchement `Database`/`default_database` pour que `import_json_to_postgres.py` fonctionne réellement (voir constat #1 ci-dessous — toujours pas fait, distinct des méthodes ajoutées cette session qui couvrent conversations/messages/reviews/memories/users, pas fiches/chunks).
- [ ] **Nouveau, critique** : résoudre l'erreur 404 sur le modèle d'embedding Gemini avant toute tentative de réindexation Qdrant (voir constat #2).
- [ ] Décider du sort de la collection Qdrant existante (3763 points, dim=1024) avant toute réindexation (voir constat #3) — vérifier d'abord si ce sont de vrais embeddings sémantiques ou des vecteurs de fallback.
- [x] ~~Les routes `app/api/agent_routes.py` ne vérifient pas le rôle/la session côté serveur~~ — fait le 2026-07-09 : `app/auth/session_token.py` (token signé HMAC-SHA256, `SESSION_SECRET`) + `app/auth/dependencies.py` (`get_current_user`, `require_ceo`). `/auth/login` et le callback OAuth renvoient désormais un `token` ; le frontend (`frontend/src/lib/api.js`) l'attache en `Authorization: Bearer` sur chaque appel. Les routes `/agent/chat`, `/agent/feedback`, `/conversations`, `/conversations/{key}/messages`, `/history` exigent une session valide et **ignorent le `user_id`/`role` envoyé dans le corps de la requête au profit de celui du token vérifié** (empêche l'usurpation CEO/SAV constatée). `/admin/reviews*`, `/agent/actions/pending|approve|reject`, `/memories/active` exigent en plus `role == "ceo"` (403 sinon). Vérifié par test (`tests/test_agent_api.py` : 401 sans token, 403 SAV sur route CEO, corps falsifié `role=ceo` avec un token SAV → le serveur utilise bien `role=sav`).
- [ ] Monter l'authentification (`OAuthService`) sur toutes les routes sensibles ; fail-closed si allowlist vide (le login local + OAuth émettent maintenant un token signé, mais `OAuthService._resolve_role` reste fail-open : si aucune allowlist n'est configurée, n'importe quel email obtient `oauth_default_role` — distinct du point ci-dessus, toujours à traiter).
- [ ] Les comptes OAuth ne sont pas persistés dans `users` (pas d'`id` réel, le token OAuth utilise `user_id=0`) — à corriger si le login social doit devenir utilisable au-delà d'un test ponctuel.
- [x] **Comptes de démo fixes ajoutés à la demande explicite de l'utilisateur** (2026-07-09) : `app/auth/local_auth_service.py::_STATIC_CREDENTIALS` — `ceo`/`ceo123` (role `ceo`) et `sav`/`sav123` (role `sav`), vérifiés **avant** tout accès à Postgres (permet de se connecter même backend/DB injoignable, cas récurrent de la VM hors ligne signalé par l'utilisateur). `id` fixes négatifs (`-1`/`-2`, pas de FK sur `conversations.user_id` donc sans risque) pour ne jamais entrer en collision avec un vrai compte Postgres. **A retirer ou protéger derrière `APP_ENV=dev` avant toute mise en production** — mots de passe faibles, jamais destinés à un usage réel.
- [ ] Configurer de vraies clés OAuth (`GOOGLE_OAUTH_CLIENT_ID/SECRET`, `FACEBOOK_OAUTH_CLIENT_ID/SECRET`) si le login social doit devenir utilisable (aujourd'hui les boutons restent désactivés faute de config).
- [ ] Supprimer les mots de passe par défaut en prod (`docker-compose.prod.yml`) ; exiger des secrets forts.
- [ ] Gater le seed Postgres (`app/db/seed.py`) derrière un flag explicite non-prod.
- [ ] Nettoyer le CSV ERP clients (ligne template mêlée aux données) et dédupliquer `data/processed/Maintenance_json` / `data/processed/maintenance`.

## Important pour stabiliser le projet

- [ ] Fusionner les deux schémas Postgres (`app/db/models.py` vs `scripts/sql/001_init_core_schema.sql`), ajouter `documents` et `sources_rag`, FK `fiches.client_id → clients.id`.
- [ ] Ajouter les index manquants (`agent_feedback`, `agent_actions`, `agent_tool_logs`), contraintes UNIQUE clients/diffuseurs.
- [ ] Ajouter l'overlap de chunking, un tokenizer réel, uniformiser la stratégie de chunking (docx compris).
- [ ] Ajouter un vrai champ page/offset et un `client_id` stable résolu une fois (au lieu du matching flou par requête).
- [ ] Ajouter du logging structuré autour des agents/outils ; brancher `ragas_runner.py` en CI.
- [ ] Ajouter TLS en prod, limites de ressources Docker, utilisateur non-root dans `Dockerfile.backend`.
- [ ] Résoudre les 762 fichiers "unmatched" du rapport de synchronisation Excel / les 270 correspondances "ignored" du rapport de similarité clients.
- [ ] Étendre significativement `data/client_name_aliases.json` (10 alias seulement pour 270+ variantes réelles).
- [ ] Étendre l'ingestion CSV à d'autres exports similaires (`Aromair_02/03/04` s'ils existent en CSV) une fois le pipeline Postgres/Qdrant réparé.

## Améliorations futures

- [ ] Contrôle de fidélité (faithfulness) au moment de la requête, pas seulement en évaluation offline.
- [ ] Citations inline dans les réponses générées.
- [ ] Vrai branchement conditionnel dans le graphe LangGraph (au-delà de l'early-exit actuel).
- [ ] Tests d'intégration bout-en-bout avec bases éphémères (testcontainers), incluant le pipeline CSV → Postgres → Qdrant une fois réparé.
- [ ] Nettoyage des fichiers parasites à la racine (scripts, notebooks, PDF, image) vers des dossiers dédiés.
- [ ] Prompt dédié recommandation + prompt de ton client-facing séparé du prompt interne.
- [ ] Interface d'inscription pour les comptes locaux si un jour nécessaire (aujourd'hui volontairement CLI-only via `scripts/create_user.py`, pas d'endpoint HTTP de création de compte exposé).

## Référence

- Audit complet initial : voir l'artefact livré en début de projet (architecture, RAG, data, PostgreSQL, Qdrant, sécurité, tests, plan d'action).
- Plan détaillé de cette session : `C:\Users\Youss\.claude\plans\giggly-leaping-matsumoto.md`.

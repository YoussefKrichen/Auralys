# Rapport Architecture et Conception Auralys

## 1. Resume executif

Auralys est une plateforme interne d'assistance operationnelle pour Aromair.
Le projet combine un backend FastAPI, une interface frontend Vue, un pipeline RAG hybride, une couche vocale et une couche agentique supervisee.
La conception privilegie une architecture modulaire, orientee services, afin de separer clairement l'ingestion de donnees, la recherche, le raisonnement, la restitution, la supervision humaine et les interfaces d'usage.

Le systeme n'est pas pense comme un simple chatbot generique.
Il est concu comme un assistant metier centre sur le SAV, l'administration, la revue de qualite et la capitalisation progressive de la connaissance operationnelle.

## 2. Finalite du projet

Les objectifs de conception identifies dans le code et la structure du projet sont les suivants :

- rendre les donnees operationnelles Aromair interrogeables rapidement
- fournir des reponses explicables a partir d'un contexte retrouve
- assister les techniciens SAV et les profils de pilotage
- supporter les interactions texte et voix
- permettre une evolution vers des actions agentiques, sans perdre le controle humain

En pratique, Auralys cherche a transformer un corpus heterogene de fiches maintenance, donnees metier et base de connaissances en un systeme d'aide a la decision exploitable.

## 3. Principes de conception

Plusieurs choix d'architecture structurent le projet :

- separation forte entre donnees brutes, donnees normalisees, index semantiques et historique conversationnel
- composition de services dans `app/bootstrap.py` plutot qu'un couplage fort entre modules
- pipeline de reponse decoupe en etapes lisibles : routage, retrieval, construction de contexte, generation, journalisation
- mode degrade possible quand le LLM distant n'est pas disponible
- supervision explicite de la couche agentique pour limiter les actions risquee
- reutilisation des briques retrieval existantes par la couche agentique au lieu de dupliquer la logique

Ce choix rend le projet plus maintenable, plus testable et plus facile a faire evoluer par couches.

## 4. Vue d'ensemble de l'architecture

L'architecture actuelle peut etre lue en sept couches principales :

- couche donnees sources : `data/raw_json`, fichiers metier et jeux de test
- couche normalisation : `app/ingestion/`
- couche stockage structure : Postgres via `app/db.py`
- couche stockage semantique : Qdrant via `app/retrieval/qdrant_retriever.py`
- couche intelligence applicative : `app/retrieval/`, `app/llm/`, `app/commercial/`, `app/history/`
- couche voix : `app/audio/speech_service.py`
- couche agentique supervisee : `app/agent/`
- couche exposition : `app/api.py`, `app/main.py`, `frontend/`

Cette stratification montre une conception orientee flux : la donnee est d'abord rendue propre, ensuite rendue consultable, puis exploitee par des services applicatifs et enfin exposee a des utilisateurs ou a des interfaces.

## 5. Backend et assemblage des dependances

Le point central d'assemblage est `app/bootstrap.py`.
Le fichier definit un `AppContainer` qui construit les services applicatifs : embeddings, retrievers SQL et Qdrant, retriever hybride, LLM, voix, historique, review et orchestrateur agentique.

Ce pattern de composition apporte trois benefices :

- centraliser le wiring technique
- simplifier les tests par injection de dependances
- garder des modules metier relativement independants

Le backend HTTP est expose par `app/api.py` avec FastAPI.
L'API couvre :

- endpoints de sante et de diagnostic
- endpoints RAG texte et audio
- endpoints d'authentification
- endpoints d'historique et de review
- endpoints agentiques de chat, feedback, approbation et memoire active

Le projet garde aussi un point d'entree CLI dans `app/main.py` pour les operations de pipeline, d'indexation, d'evaluation et d'usage vocal local.

## 6. Pipeline de donnees

La conception de la donnee est un point fort du projet.
Le systeme ne consomme pas directement les fichiers bruts au moment de la reponse.
Il passe par une chaine de transformation :

- ingestion de fichiers source dans `data/raw_json`
- normalisation vers des fiches homogenes via `app/ingestion/normalize.py`
- export de sorties structurees dans `data/processed` et `data/processed_csv`
- generation de chunks avec `app/ingestion/build_chunks.py`
- chargement des structures exactes dans Postgres
- indexation semantique des chunks dans Qdrant

Cette conception permet de separer :

- la verite source
- la representation metier normalisee
- la representation retrieval
- la representation conversationnelle et analytique

Autrement dit, Auralys est pense comme un systeme de donnees exploitable, pas comme une simple surcouche conversationnelle.

## 7. Strategie de retrieval

Le coeur de la logique de reponse repose sur un retrieval hybride.
Le code `app/retrieval/hybrid_retriever.py` combine plusieurs strategies :

- SQL pour les recherches precises, filtrees et structurees
- Qdrant pour la recherche semantique dense
- local fallback pour conserver une capacite de secours sur les donnees traitees

Le routage initial est gere par `app/retrieval/query_router.py`.
Cette etape detecte l'intention, normalise la requete et choisit la route de recherche adaptee.

Le choix de conception ici est important :

- ne pas forcer un unique moteur de recherche
- exploiter SQL pour l'exactitude
- exploiter le vectoriel pour la similarite semantique
- conserver une resilience locale quand les stores externes ne renvoient pas assez de signal

Cette approche est plus robuste qu'un RAG purement vectoriel, en particulier pour des donnees metier semi-structurees.

## 8. Generation de reponse et instrumentation

La couche `app/llm/answer_service.py` orchestre la reponse finale.
Le flux principal est le suivant :

- routage de la requete
- recherche des hits
- construction du contexte
- analyse commerciale ou d'opportunite
- appel LLM
- calcul de metriques et de signaux de raisonnement
- production d'une reponse exploitable et historisable

La conception ne se limite pas a "poser une question au modele".
Le systeme produit aussi :

- `response_source`
- `model_output`
- `llm_error`
- `token_usage`
- `timings`
- `relevance_metrics`
- `reasoning_signals`
- `spoken_text`

Ce point est architecturalement important car il rend le systeme observable.
On peut distinguer la qualite du retrieval, la qualite du modele, les temps de traitement et la forme finale de restitution.

## 9. Couche vocale

La composante `app/audio/speech_service.py` montre une conception orientee usage terrain.
Le projet prend en charge :

- transcription audio
- synthese vocale
- capture micro en temps reel
- tours vocaux complets avec transcription, reponse et restitution

La couche voix supporte plusieurs backends :

- `pyttsx3` pour les voix systeme
- `Piper` pour une voix locale plus naturelle
- `Gemini` pour certains usages TTS selon la configuration

Le point cle de conception est que la voix n'est pas un module cosmetique.
Elle est integree au pipeline applicatif avec des sorties dediees comme `spoken_text`, la gestion du wake word, la detection de silence et la possibilite de conserver ou non les fichiers audio.

## 10. Couche agentique supervisee

Le dossier `app/agent/` introduit une couche agentique beta composee de :

- routage d'intention
- orchestration de session
- memoire active
- outils ERP, RAG, cartes et memoire
- skills specialises SAV, historique client, alertes, diagnostic et reporting CEO
- politique d'action via `app/agent/policies/action_policy.py`
- persistence des conversations, feedbacks, actions, memoires et logs

La conception ici est prudente.
Le projet ne laisse pas l'agent agir librement par defaut.
Il applique une logique de supervision et d'approbation humaine pour les actions sensibles.

Ce choix est coherent avec un contexte metier reel :

- les recommandations peuvent etre automatisees
- les actions a impact doivent rester controlees

Architecturalement, c'est un bon compromis entre assistance avancee et gouvernance.

## 11. Frontend et experience utilisateur

Le frontend repose sur Vue et Vite dans `frontend/`.
Le fichier `frontend/src/App.vue` montre une interface orientee role avec au moins deux espaces :

- espace SAV
- espace CEO

La conception front n'est donc pas neutre.
Elle suit une logique de separation par profil d'usage, avec navigation, session locale, pages de connexion et zones de travail distinctes.

Ce choix aligne l'interface avec l'architecture metier :

- le SAV consomme des outils d'assistance operationnelle
- la direction consomme des outils de revue, qualite et pilotage

## 12. Infrastructure et deploiement

Le fichier `docker-compose.yml` montre deux briques d'infrastructure principales :

- Postgres
- Qdrant

La pile applicative elle-meme peut tourner localement via Python pour le backend et Node/Vite pour le frontend.
Cette separation entre services de donnees conteneurises et application locale facilite le developpement iteratif.

La conception d'infrastructure est simple mais adaptee au stade actuel du projet :

- un store relationnel pour l'exact
- un store vectoriel pour le semantique
- une application backend modulaire
- un frontend web leger

## 13. Forces de l'architecture

Les forces principales du projet sont les suivantes :

- modularite claire entre ingestion, retrieval, LLM, voix, agent et interfaces
- hybridation SQL plus vectoriel pertinente pour des donnees SAV
- presence d'un mode degrade et d'une observabilite utile
- couche vocale integree a la logique produit
- agenticite supervisee, mieux adaptee au risque metier
- existence de tests cibles sur retrieval, pipeline et agent
- coexistence CLI plus API plus frontend, utile pour les usages differencies

## 14. Limites et points de vigilance

L'architecture reste solide, mais quelques limites structurantes apparaissent :

- `AppContainer` construit les dependances de maniere repetitive et sans cycle de vie partage, ce qui peut devenir couteux a mesure que les services grossissent
- la couche agentique, la couche review et la couche RAG coexistent bien, mais leur gouvernance commune peut encore etre formalisee davantage
- la qualite retrieval depend fortement de la qualite de normalisation et des metadonnees de chunks
- la presence de plusieurs modes LLM et TTS exige une discipline de configuration et de validation
- le projet melange deja assistance operationnelle, reporting, review et agenticite ; une clarification plus explicite des bounded contexts pourra aider la suite

Ces points ne remettent pas en cause la conception generale, mais indiquent les zones a structurer si le projet passe a une echelle plus large.

## 15. Recommandations de conception pour la suite

Pour renforcer l'architecture, les evolutions les plus utiles seraient :

- formaliser une cartographie des domaines metier : SAV, revue qualite, pilotage, agent actions, knowledge management
- introduire progressivement des interfaces de service plus explicites entre retrieval, review et agent
- stabiliser un modele canonique des entites metier importantes : client, intervention, fiche, action, conversation, alerte
- mieux factoriser la creation des dependances couteuses dans le container
- etendre la strategie d'observabilite avec traces plus uniformes entre API, agent et voix
- definir un protocole de tests end-to-end couvrant texte, voix et actions agentiques

## 16. Conclusion

Auralys presente une architecture serieuse, deja au-dela d'un prototype de chatbot.
Sa conception repose sur un enchainement coherent :

- rendre la donnee propre
- la rendre recherchable par plusieurs strategies
- construire un contexte utile
- generer une reponse tracable
- exposer cette intelligence dans des interfaces texte, voix et agentiques

Le projet se distingue particulierement par trois choix de conception justes :

- un RAG hybride au lieu d'un vectoriel pur
- une couche voix integree au produit
- une agenticite supervisee plutot qu'autonome par defaut

Dans son etat actuel, Auralys peut etre qualifie de plateforme d'assistance metier modulaire, extensible et deja bien alignee avec un usage operationnel reel.

# Rapport Application Auralys

## 1. Resume executif

Auralys est une application d'assistance interne destinee a l'equipe SAV et a l'administration d'Aromair.
Son objectif est d'aider a la prise de decision, a la verification de points critiques, a la recommandation de diffuseurs et a l'escalade interne des opportunites ou des situations qui necessitent un suivi.

L'application fonctionne en texte et en vocal.
Elle peut exploiter des donnees de maintenance, un catalogue de diffuseurs, des recherches hybrides SQL + Qdrant, une couche de raisonnement LLM et des fonctions d'evaluation via RAGAS et LangSmith.

## 2. Objectif metier

- Assister le SAV dans les diagnostics et recommandations operationnelles.
- Assister l'administration dans la verification de devis, de suivis et de points d'escalade.
- Recommander des diffuseurs adaptes selon le contexte d'usage.
- Fournir des reponses utilisables a l'ecrit comme a l'oral.
- Ameliorer la qualite de service et soutenir un bilan positif pour la societe.

## 3. Positionnement fonctionnel

Auralys n'est pas un chatbot client final.
Il s'agit d'un assistant interne qui :

- guide les techniciens SAV
- aide l'administration a verifier des points
- propose des actions ou produits adaptes
- met en evidence les informations manquantes
- peut signaler une opportunite interne ou une demande de devis

## 4. Architecture applicative

L'application est organisee autour des briques suivantes :

- `app/main.py` : point d'entree CLI
- `app/bootstrap.py` : assemblage des services
- `app/ingestion/` : chargement, normalisation et preparation des donnees
- `app/retrieval/` : routage, recherche SQL, recherche vectorielle et fusion hybride
- `app/llm/` : generation de prompt et production de reponse
- `app/audio/` : transcription, synthese vocale et capture micro temps reel
- `app/evaluation/` : evaluation locale et LangSmith
- `schemas/` : schemas de donnees et de pipeline

## 5. Donnees exploitees

L'application consomme actuellement :

- des fiches de maintenance JSON
- un catalogue de diffuseurs JSON
- des jeux d'evaluation pour les cas texte et vocaux

Etat releve dans le projet :

- nombre total de fiches : 126
- nombre de clients uniques : 118
- types de service les plus frequents : livraison, visite, reparation, echange

## 6. Recherche et recommandation

Le moteur de recherche utilise une approche hybride :

- SQL pour les recherches precises et le texte structure
- Qdrant pour la recherche semantique
- fusion de resultats pour construire le contexte final

En complement, un module de catalogue produit permet de recommander des diffuseurs en fonction de :

- la surface
- le type de lieu
- le positionnement premium
- les usages cibles du diffuseur

Exemple de recommandation actuellement obtenue :

- hotel 500 m2 : Aromair500 puis Aromair600
- grand espace premium : Aromair600 puis Iceberg

## 7. Voix et temps reel

Auralys prend en charge :

- la transcription d'un fichier audio
- la synthese de reponse audio
- un mode `live-voice` pour capter un tour micro en temps reel, transcrire, repondre et parler immediatement
- un backend vocal Windows `pyttsx3` pour les voix systeme
- un backend vocal neural local `Piper` pour une voix plus naturelle et exploitable hors ligne
- une prise en compte explicite du mode `hands-free` pour des reponses vocales comprehensibles sans support visuel

Salutation par defaut :

- `Bonjour, je suis Auralys, comment puis-je vous aider ?`

Etat actuellement valide :

- detection des voix systeme locales
- selection et priorisation des voix francaises quand `pyttsx3` est utilise
- integration de `Piper` avec un modele francais local
- generation de fichiers WAV de test pour valider la diction
- normalisation du texte vocal pour eviter une lecture trop brute ou trop mecanique
- cadrage du ton et de la structure de reponse pour les usages sans ecran

Exemple de voix locale testee :

- `fr_FR-siwis-medium` via Piper

Constat de test vocal :

- l'intelligibilite generale est bonne
- le rendu oral est plus naturel qu'avec la voix systeme par defaut
- certains noms propres comme `Auralys` peuvent encore necessiter un traitement phonetic explicite

## 8. Cas d'usage couverts

- recommandation de diffuseur
- diagnostic SAV
- verification d'une fuite
- verification de points avant validation
- preparation d'un devis interne
- verification des informations manquantes
- assistance vocale pour technicien ou administration

## 9. Evaluation

Le projet contient un dataset d'evaluation structure :

- total d'exemples : 27
- cas vocaux : 6
- cas admin_verification : 4

Les evaluations disponibles :

- RAGAS
- LangSmith dataset sync
- LangSmith evaluation

## 10. Ameliorations recentes

- alignement du role sur un usage SAV/admin
- salutation systematique en francais
- recommandation produit basee sur le catalogue
- correction du routage des requetes naturelles
- fallback local plus utile pour les cas SAV
- exposition d'une analyse `sav_admin_analysis`
- ajout d'un mode vocal temps reel
- production d'une reponse plus coherente entre texte affiche et texte lu a voix haute
- normalisation de `spoken_text` a partir de la reponse finale plutot qu'a partir d'un chunk brut
- ajout d'un backend `Piper` parametrable via la configuration
- ajout de reglages voix avances : volume, modele Piper, speaker, longueur, bruit et normalisation audio
- ajout d'une tracabilite de reponse avec `response_source`, `model_output` et `llm_error`
- correction de l'appel HTTP Groq par ajout d'un `User-Agent` pour contourner un blocage Cloudflare `403 / 1010`
- ajout d'un principe `hands-free` dans la configuration et le prompt pour guider les reponses vocales sans dependance a l'ecran

## 11. LLM et mode degrade

La couche LLM fonctionne desormais en deux modes explicites :

- mode `groq` lorsque la requete distante reussit
- mode `fallback` lorsque la cle est absente ou que l'appel distant echoue

Le pipeline expose maintenant dans la reponse :

- `response_source` pour savoir si la reponse provient de Groq ou du fallback local
- `model_output` pour afficher la sortie brute du modele Groq
- `llm_error` pour diagnostiquer la raison d'un echec distant

Cette instrumentation facilite :

- le debug des appels LLM
- la comparaison entre sortie generee et sortie degradee
- la validation du comportement reel de l'application en demonstration

## 12. Points forts actuels

- architecture claire et modulaire
- support texte et voix
- recherche hybride
- recommandations produit deja operationnelles sur plusieurs cas
- evaluations deja integrees
- fonctionnement degrade possible meme sans LLM distant
- observabilite amelioree sur la vraie source de la reponse LLM
- backend vocal local neural disponible sans dependance cloud

## 13. Limites actuelles

- certains textes de contexte brut restent en anglais car issus des donnees ou des chunks historiques
- la pertinence retrieval peut encore etre amelioree pour certains cas tres operationnels
- le log d'opportunites existant contient encore une entree historique non harmonisee
- les tests vocaux valident surtout les prompts vocaux, pas encore un protocole complet de tests audio reels automatises
- la reponse Groq reste parfois plus longue et plus commerciale que souhaite pour un usage SAV/admin strict
- la prononciation des noms propres et marques n'est pas encore entierement maitrisee en synthese locale
- le mode fallback reste base sur des regles simples et non sur un second modele local

## 14. Recommandations

- renforcer encore le classement des resultats retrieval
- harmoniser les contenus historiques normalises
- ajouter des tests automatiques centres sur SAV/admin
- etendre le dataset vocal
- ajouter un mode de conversation continue avec detection de silence
- durcir le prompt pour obtenir des reponses Groq plus courtes, plus operationnelles et moins verbeuses
- ajouter un traitement de prononciation dedie pour les termes de marque comme `Auralys`, `Aromair500` ou `Zee300`
- mettre en place un protocole de comparaison systematique `pyttsx3` vs `Piper`
- ajouter un indicateur de confiance ou de qualite percue sur les sorties vocales et LLM

## 15. Conclusion

Auralys constitue deja une base fonctionnelle solide pour une assistance interne SAV et administration.
L'application sait traiter des questions texte et vocales, recommander des diffuseurs, donner des reponses de securisation ou de verification, et exposer une analyse structurante utile au metier.

La direction prise est coherent avec l'objectif d'un assistant interne decisionnel, exploitable sur le terrain et extensible.
Les ajouts recents sur la voix locale, la traçabilite LLM et la fiabilisation de l'integration Groq renforcent nettement la maturite technique de la solution.

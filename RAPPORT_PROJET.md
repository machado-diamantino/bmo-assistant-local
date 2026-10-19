# Rapport de préparation GitHub — BMO

Date d’audit : 19 octobre 2026  
Périmètre : dossier `agent_ia/`

## Résumé

BMO est une application Python monofichier destinée à un Raspberry Pi équipé d’un écran et d’une sortie audio. L’application lance une interface Pygame plein écran, appelle Ollama localement pour le dialogue et la vision, utilise Piper pour générer la voix et lit un flux DroidCam via OpenCV.

L’application passe la vérification de syntaxe Python (`py_compile`). Les dépendances installées ont été relevées et verrouillées dans `requirements.txt`. Une documentation d’installation et une politique d’exclusion Git ont été ajoutées.

## Architecture constatée

| Composant | Implémentation | Rôle |
| --- | --- | --- |
| Interface | Pygame | Écran plein format, saisie texte, boutons et animation |
| Dialogue | Ollama + `qwen3:0.6b` | Réponse conversationnelle en français |
| Vision | OpenCV + DroidCam + `moondream` | Lecture vidéo et description d’image |
| Voix | Piper | Synthèse de la réponse au format WAV |
| Mémoire | `memory.json` | Douze messages maximum conservés localement |
| Démarrage | script `bmo` | Exécute le Python de l’environnement virtuel |

## Fichiers à publier

À placer à la racine d’un dépôt GitHub nommé par exemple `bmo-ai` :

```text
bmo
bmo_ultimate_v6.py
requirements.txt
README.md
RAPPORT_PROJET.md
.gitignore
memory.example.json
images/
  idle/
  talk/
  think/
```

Les trois documents ODT existants peuvent être ajoutés dans un dossier `docs/archives/` si vous souhaitez conserver l’historique du projet. Ils sont utiles comme notes personnelles mais ne reflètent pas complètement la version actuelle : ils citent notamment d’anciens noms de scripts et modèles.

## Fichiers à ne pas publier

| Élément | Motif |
| --- | --- |
| `venv/` | Environnement Python local, lourd et reproductible avec `requirements.txt` |
| `__pycache__/` et `*.pyc` | Cache généré automatiquement |
| `memory.json` | Historique personnel des conversations |
| `:memory:.ses` | Fichier temporaire local |
| `voices/fr_FR-siwis-medium.onnx*` | Modèle binaire de 63 Mo à télécharger séparément et soumis à ses propres conditions |
| `rapport` | Fichier vide, remplacé par ce rapport Markdown |

Les dossiers voisins `traducteur-dash/` et `image_bmo/` ne font pas partie du dépôt BMO : le premier est une autre application et le second contient seulement des images sources en double.

## Risques et améliorations prioritaires

1. L’adresse de la caméra est écrite en dur dans le code. La passer dans un fichier `.env` ou un fichier de configuration rendrait l’installation plus sûre et portable.
2. Les exceptions sont parfois silencieusement ignorées. Un affichage d’erreur et des journaux structurés faciliteraient le diagnostic sur Raspberry Pi.
3. Il n’y a pas encore de tests automatisés ni de contrôle de formatage.
4. Les fonctionnalités citées dans les premières notes — micro/STT, météo et prise de photo — ne sont pas encore implémentées dans cette version.
5. Le dépôt doit recevoir une licence choisie par son auteur avant publication publique.

## Vérification avant publication

```bash
cd agent_ia
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m py_compile bmo_ultimate_v6.py
git init
git add .
git status
```

Vérifiez dans la dernière commande que ni `venv/`, ni `memory.json`, ni les modèles `voices/*.onnx*` ne sont prêts à être ajoutés.

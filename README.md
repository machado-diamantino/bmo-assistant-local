# BMO — assistant IA local pour Raspberry Pi

BMO est un assistant personnel local, avec une interface animée inspirée du personnage BMO. Il s’exécute sur Linux/Raspberry Pi, répond en français via Ollama, parle avec Piper et peut analyser le flux d’une caméra DroidCam avec un modèle de vision local.

> Le projet est actuellement une application de bureau plein écran contrôlée au clavier et à la souris. Il ne contient pas encore de reconnaissance vocale, de météo, de prise de photo ni de commande Bluetooth dédiée.

## Fonctionnalités

- Conversation locale en français avec `qwen3:0.6b` exécuté par Ollama.
- Mémoire locale courte des six derniers échanges.
- Synthèse vocale hors ligne avec Piper.
- États animés : repos, réflexion et parole.
- Vision depuis DroidCam et description de l’image par `moondream`.
- Boutons rapides : heure, caméra, explication, mémoire et arrêt.

## Prérequis

- Raspberry Pi OS/Debian ou une distribution Linux avec affichage graphique.
- Python 3.11 ou plus récent.
- [Ollama](https://ollama.com/) installé et actif.
- Une sortie audio configurée pour Pygame.
- Facultatif : DroidCam accessible sur le réseau pour la vision.

Télécharger les modèles Ollama nécessaires :

```bash
ollama pull qwen3:0.6b
ollama pull moondream
```

Télécharger ensuite une voix française Piper et placer ses deux fichiers dans `voices/` :

```text
voices/fr_FR-siwis-medium.onnx
voices/fr_FR-siwis-medium.onnx.json
```

Le nom et l’emplacement sont importants : ils correspondent à la configuration actuelle du script. Les modèles vocaux ne sont volontairement pas versionnés ; ils sont volumineux et disposent de leurs propres conditions de distribution.

## Installation

```bash
git clone https://github.com/VOTRE_COMPTE/bmo-ai.git
cd bmo-ai
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Dans un autre terminal, lancez le service Ollama si nécessaire :

```bash
ollama serve
```

## Configuration

Avant le premier lancement :

1. Copiez `memory.example.json` vers `memory.json` si vous souhaitez initialiser une mémoire vide. Sinon, BMO créera ce fichier à la première conversation.
2. Installez les deux modèles Ollama indiqués ci-dessus.
3. Téléchargez la voix Piper aux chemins indiqués dans la section Prérequis.
4. Pour activer la vision, adaptez `IP_CAMERA` dans `bmo_ultimate_v6.py` à l’adresse IP du téléphone utilisant DroidCam. L’URL attendue est `http://<IP>:4747/video`.

## Lancer BMO

```bash
chmod +x bmo
./bmo
```

Ou directement :

```bash
venv/bin/python bmo_ultimate_v6.py
```

`Échap` ferme l’application. Les boutons de l’interface offrent les actions les plus courantes. Pour la caméra, activez-la une première fois, puis posez une question de vision (par exemple : « quelle couleur est mon t-shirt ? »).

## Arborescence

```text
.
├── bmo                       # Lanceur Linux
├── bmo_ultimate_v6.py        # Application principale
├── images/                   # Images d’animation Pygame
│   ├── idle/
│   ├── talk/
│   └── think/
├── voices/                   # Modèles Piper locaux (ignorés par Git)
├── memory.example.json       # Modèle de mémoire vide
├── requirements.txt          # Dépendances Python verrouillées
└── README.md
```

## Confidentialité

Les conversations sont envoyées à Ollama sur la machine locale. `memory.json` conserve les derniers échanges sur le disque ; il est ignoré par Git et ne doit pas être publié. La caméra reste locale mais son flux dépend de la configuration DroidCam et du réseau utilisé.

## État et pistes d’évolution

Le cœur conversationnel, l’interface, la voix et la vision sont présents. Les priorités recommandées sont la configuration par fichier d’environnement, des messages d’erreur visibles, des tests automatisés et l’implémentation réelle de la reconnaissance vocale et de la météo évoquées dans les notes de conception.

## Licence

Aucune licence n’est encore choisie. Ajoutez une licence explicite avant de rendre le dépôt public afin d’indiquer clairement les droits de réutilisation.

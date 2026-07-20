#!/bin/bash

# Récupération du chemin absolue
ABSOLUTE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Déplacement dans le dossier du script 
cd "$ABSOLUTE_PATH"

# Calcul du nom du dossier 2 rangs au-dessus
export PROJECT_NAME="$(basename "$(dirname "$(dirname "$ABSOLUTE_PATH")")")"

# Chemin vers le fichier .env de la racine
ENV_FILE="../.env"

# Chargement du .env 
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "Erreur : le fichier .env n'a pas été trouvé à l'emplacement : $ENV_FILE"
    exit 1
fi

# Lancement de docker compose 
docker compose stop
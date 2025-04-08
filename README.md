# Automatisation Demandes de Mandat

Ce dépôt contient un script d'automatisation pour la gestion des demandes de mandat via Airtable et Sellsy.

## Fonctionnalités

- Vérifie périodiquement Airtable pour les nouveaux contrats signés
- Récupère les informations clients depuis Sellsy
- Envoie un email personnalisé avec lien GoCardless pour la création du mandat
- Met à jour Airtable après l'envoi de l'email

## Configuration

### GitHub Secrets

Les informations sensibles sont stockées dans des secrets GitHub. Vous devez configurer les secrets suivants :

- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `AIRTABLE_TABLE_NAME` 
- `AIRTABLE_INSTALLERS_BASE_ID`
- `AIRTABLE_INSTALLATEURS_TABLE`
- `SELLSY_CONSUMER_TOKEN`
- `SELLSY_CONSUMER_SECRET`
- `SELLSY_USER_TOKEN`
- `SELLSY_USER_SECRET`
- `GOCARDLESS_DIRECT_LINK`

### Workflow GitHub Actions

Le script est exécuté automatiquement toutes les 5 minutes via GitHub Actions.

## Développement local

Pour exécuter localement :

1. Clonez ce dépôt
2. Créez un fichier `.env` avec les variables nécessaires
3. Installez les dépendances : `pip install -r requirements.txt`
4. Exécutez le script : `python mandate_checker.py`

## Structure du code

- `mandate_checker.py` - Script principal
- `.github/workflows/mandate-check.yml` - Configuration du workflow GitHub Actions
- `requirements.txt` - Dépendances Python

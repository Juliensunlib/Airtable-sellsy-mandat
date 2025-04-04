from dotenv import load_dotenv
import os
import time
import requests
import json
from datetime import datetime

# Chargement des variables d'environnement
load_dotenv()

# Configuration des API depuis les variables d'environnement
# Pour Airtable
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")

# Pour Sellsy
SELLSY_CONSUMER_TOKEN = os.getenv("SELLSY_CONSUMER_TOKEN")
SELLSY_CONSUMER_SECRET = os.getenv("SELLSY_CONSUMER_SECRET")
SELLSY_USER_TOKEN = os.getenv("SELLSY_USER_TOKEN")
SELLSY_USER_SECRET = os.getenv("SELLSY_USER_SECRET")

# Paramètres de l'application
LOG_DIR = os.getenv("LOG_DIR", "logs")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 minutes par défaut

# URL de l'API
AIRTABLE_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
SELLSY_API_URL = "https://api.sellsy.com/v2/public/api/index.php"

# Fonction pour enregistrer les logs
def log_activity(message):
    log_path = os.path.join(LOG_DIR)
    
    # Créer le dossier logs s'il n'existe pas
    if not os.path.exists(log_path):
        os.makedirs(log_path)
        
    log_file = os.path.join(log_path, f"log_{datetime.now().strftime('%Y-%m-%d')}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    
    print(message)

# Fonction pour vérifier les changements dans Airtable
def check_airtable_changes():
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    log_activity("Vérification des changements Airtable...")
    
    response = requests.get(
        AIRTABLE_API_URL,
        headers=headers
    )
    
    if response.status_code == 200:
        records = response.json().get("records", [])
        contract_signed_count = 0
        
        for record in records:
            fields = record.get("fields", {})
            record_id = record.get("id", "inconnu")
            
            # Vérifie si le champ "Contrat abonnement signe" est rempli (True ou toute autre valeur non vide)
            if fields.get("Contrat abonnement signe"):
                contract_signed_count += 1
                customer_email = fields.get("Email", "Non spécifié")
                customer_id = fields.get("ID_Sellsy", "Non spécifié")
                customer_name = fields.get("Nom", "Client")
                
                log_activity(f"Contrat signé détecté pour: {customer_name} (Email: {customer_email}, ID Sellsy: {customer_id}, Record: {record_id})")
                
                # Déclencher l'envoi d'email via Sellsy
                send_sellsy_email(customer_email, customer_id, customer_name)
        
        log_activity(f"Vérification terminée - {contract_signed_count} contrats signés trouvés sur {len(records)} enregistrements.")
    else:
        log_activity(f"Erreur lors de l'accès à Airtable: {response.status_code}")
        log_activity(f"Détails: {response.text}")

# Fonction pour envoyer un email via Sellsy (sans utiliser le template GoCardless)
def send_sellsy_email(customer_email=None, customer_id=None, customer_name="Client"):
    log_activity(f"Envoi d'email pour {customer_name}...")
    
    # Génération des paramètres d'authentification pour Sellsy
    nonce = str(int(time.time()))
    
    # Préparation de la requête
    sellsy_request = {
        "method": "Emails.sendOne",
        "params": {
            # Si vous avez l'ID client Sellsy
            "clientid": customer_id if customer_id and customer_id != "Non spécifié" else "",
            
            # Si vous avez seulement l'email
            "email": customer_email if customer_email and customer_email != "Non spécifié" else "",
            
            # Information sur l'email à envoyer
            "subject": "Invitation mandat GoCardless",
            "message": f"Bonjour {customer_name},\n\nVotre contrat d'abonnement a été signé. Veuillez compléter votre mandat GoCardless.\n\nCordialement,\nL'équipe"
            
            # Nous avons supprimé les lignes suivantes pour envoyer directement depuis Sellsy sans GoCardless
            # "module": "gocardless",
            # "templateid": "YOUR_GOCARDLESS_TEMPLATE_ID"
        }
    }
    
    encoded_request = json.dumps(sellsy_request)
    
    # Préparation des données d'authentification
    oauth_params = {
        "oauth_consumer_key": SELLSY_CONSUMER_TOKEN,
        "oauth_token": SELLSY_USER_TOKEN,
        "oauth_nonce": nonce,
        "oauth_timestamp": nonce,
        "oauth_signature_method": "PLAINTEXT",
        "oauth_version": "1.0",
        "oauth_signature": f"{SELLSY_CONSUMER_SECRET}&{SELLSY_USER_SECRET}",
        "io_mode": "json",
        "do_in": encoded_request
    }
    
    # Envoi de la requête à Sellsy
    try:
        response = requests.post(SELLSY_API_URL, data=oauth_params)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                log_activity(f"Email envoyé avec succès via Sellsy pour {customer_name}")
            else:
                log_activity(f"Erreur lors de l'envoi de l'email pour {customer_name}: {result.get('error')}")
                log_activity(f"Détails de l'erreur: {json.dumps(result, indent=2)}")
        else:
            log_activity(f"Erreur lors de l'accès à Sellsy: {response.status_code}")
            log_activity(f"Détails: {response.text}")
    except Exception as e:
        log_activity(f"Exception lors de l'envoi de l'email: {str(e)}")

# Boucle principale pour vérifier périodiquement les changements
def main():
    log_activity("Démarrage de la surveillance Airtable...")
    log_activity(f"Utilisation du dossier logs: {os.path.abspath(LOG_DIR)}")
    
    try:
        while True:
            check_airtable_changes()
            log_activity(f"En attente du prochain contrôle dans {CHECK_INTERVAL} secondes...")
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        log_activity("Surveillance arrêtée par l'utilisateur")
    except Exception as e:
        log_activity(f"Erreur dans la boucle principale: {str(e)}")

if __name__ == "__main__":
    main()
import os
import time
import requests
import json
from datetime import datetime
try:
    from dotenv import load_dotenv
    load_dotenv()  # Essayer de charger depuis .env si disponible
except:
    pass  # Continuer même si le fichier .env n'existe pas ou si le module n'est pas installé

# Configuration des API depuis les variables d'environnement et nettoyage des valeurs
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "").strip()
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "").strip()
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "").strip()

# Configuration de la base de données spécifique pour les installateurs
AIRTABLE_INSTALLERS_BASE_ID = os.getenv("AIRTABLE_INSTALLERS_BASE_ID", "").strip()
AIRTABLE_INSTALLATEURS_TABLE = os.getenv("AIRTABLE_INSTALLATEURS_TABLE", "Installateurs").strip()

SELLSY_CONSUMER_TOKEN = os.getenv("SELLSY_CONSUMER_TOKEN", "").strip()
SELLSY_CONSUMER_SECRET = os.getenv("SELLSY_CONSUMER_SECRET", "").strip()
SELLSY_USER_TOKEN = os.getenv("SELLSY_USER_TOKEN", "").strip()
SELLSY_USER_SECRET = os.getenv("SELLSY_USER_SECRET", "").strip()

# Lien direct GoCardless
GOCARDLESS_DIRECT_LINK = os.getenv("GOCARDLESS_DIRECT_LINK", "https://pay.gocardless.com/BRT0003FA5F2M1Q").strip()

# ID du template d'email dans Sellsy
SELLSY_EMAIL_TEMPLATE_ID = "74"  # ID du template "Demande de mandat API"

# Paramètres de l'application
LOG_DIR = os.getenv("LOG_DIR", "logs")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 min par défaut

# URLS des APIs
AIRTABLE_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
AIRTABLE_INSTALLERS_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_INSTALLERS_BASE_ID}/{AIRTABLE_INSTALLATEURS_TABLE}"
SELLSY_API_URL = "https://apifeed.sellsy.com/0/"

# Fonction de log
def log_activity(message):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    log_file = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y-%m-%d')}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)

# Vérifie les enregistrements Airtable
def check_airtable_changes():
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    log_activity("📡 Début de la vérification des changements Airtable (pagination activée)...")

    records = []
    offset = None

    while True:
        url = AIRTABLE_API_URL
        if offset:
            url += f"?offset={offset}"

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
        else:
            log_activity(f"❌ Erreur Airtable pendant la récupération paginée : {response.status_code} - {response.text}")
            break

    log_activity(f"🔍 {len(records)} enregistrements récupérés au total")

    for record in records:
        fields = record.get("fields", {})
        record_id = record.get("id")
        
        if fields.get("Contrat abonnement signe") and not fields.get("Email Mandat sellsy"):
            customer_name = fields.get("Nom", "Client")
            customer_email = fields.get("Email")
            customer_id = fields.get("ID_Sellsy", "").strip()
            installer_raw = fields.get("Installateur", "")
            signature_date = fields.get("Date de signature de contrat", "")
            
            installer_name = get_installer_name(installer_raw)

            log_activity(f"📨 Préparation de l'email avec lien GoCardless direct pour : {customer_name} (Email: {customer_email}, ID Sellsy: {customer_id})")
            
            process_mandate_request(
                client_id=customer_id,
                record_id=record_id,
                installer_name=installer_name,
                signature_date=signature_date
            )
        elif fields.get("Email Mandat sellsy"):
            log_activity(f"⏩ Invitation déjà envoyée pour {fields.get('Nom', 'Client')}, on ignore.")

    else:
        log_activity(f"❌ Erreur d'Airtable : {response.status_code} - {response.text}")

# Récupère le nom d'un installateur à partir d'un ID ou d'une liste d'IDs
def get_installer_name(installer_data):
    # Si c'est une chaîne de caractères
    if isinstance(installer_data, str):
        # Si c'est un ID Airtable, récupérer le nom depuis la base Airtable
        if installer_data.startswith("rec"):
            return get_installer_name_from_airtable(installer_data)
        return installer_data
    
    # Si c'est une liste d'IDs
    elif isinstance(installer_data, list) and len(installer_data) > 0:
        first_id = installer_data[0]
        if isinstance(first_id, str) and first_id.startswith("rec"):
            return get_installer_name_from_airtable(first_id)
        return str(first_id)
    
    # Valeur par défaut
    return "Installateur non spécifié"

# Récupère le nom de l'installateur depuis Airtable
def get_installer_name_from_airtable(installer_id):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    url = f"{AIRTABLE_INSTALLERS_API_URL}/{installer_id}"
    
    try:
        log_activity(f"🔍 Récupération de l'installateur depuis: {url}")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            installer_data = response.json()
            installer_name = installer_data.get("fields", {}).get("Nom", "Installateur non spécifié")
            log_activity(f"✅ Nom de l'installateur récupéré: {installer_name}")
            return installer_name
        else:
            log_activity(f"❌ Erreur lors de la récupération du nom de l'installateur: {response.status_code} - {response.text}")
            # Utiliser une valeur de repli si la récupération échoue
            return "Installateur"
    except Exception as e:
        log_activity(f"❌ Exception lors de la récupération du nom de l'installateur: {str(e)}")
        return "Installateur"

# Récupère les informations client depuis Sellsy
def get_customer_info_from_sellsy(client_id):
    log_activity(f"🔍 Récupération des informations client de Sellsy pour l'ID {client_id}...")
    
    # On essaie d'abord avec l'ID en tant que chaîne
    client_info = _get_sellsy_client(client_id)
    
    # Si ça échoue, on essaie avec l'ID converti en entier si possible
    if client_info is None:
        try:
            int_client_id = int(client_id)
            log_activity(f"🔄 Tentative avec ID converti en entier: {int_client_id}")
            # Attendre une seconde pour éviter les problèmes de nonce
            time.sleep(1)
            client_info = _get_sellsy_client(int_client_id)
        except ValueError:
            log_activity(f"❌ Impossible de convertir l'ID client '{client_id}' en entier")
    
    return client_info

# Fonction interne pour l'appel API Sellsy
def _get_sellsy_client(client_id):
    # Utiliser le timestamp avec millisecondes pour avoir un nonce vraiment unique
    nonce = str(int(time.time() * 1000))
    
    sellsy_request = {
        "method": "Client.getOne",
        "params": {
            "clientid": client_id
        }
    }
    
    log_activity(f"🔧 Paramètres requête Sellsy: {json.dumps(sellsy_request)}")
    
    oauth_params = {
        "oauth_consumer_key": SELLSY_CONSUMER_TOKEN,
        "oauth_token": SELLSY_USER_TOKEN,
        "oauth_nonce": nonce,
        "oauth_timestamp": nonce,
        "oauth_signature_method": "PLAINTEXT",
        "oauth_version": "1.0",
        "oauth_signature": f"{SELLSY_CONSUMER_SECRET}&{SELLSY_USER_SECRET}",
        "io_mode": "json",
        "do_in": json.dumps(sellsy_request)
    }
    
    try:
        response = requests.post(SELLSY_API_URL, data=oauth_params)
        log_activity(f"📊 Code de réponse Sellsy: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            log_activity(f"📝 Réponse Sellsy: {json.dumps(result)[:200]}...")  # Affiche les 200 premiers caractères
            
            if result.get("status") == "success":
                client_data = result.get("response", {})
                
                # Extraire les informations nécessaires à partir de la structure correcte
                corporation = client_data.get("corporation", {})
                contact = client_data.get("contact", {})
                
                # Extraction correcte des données de la réponse Sellsy
                customer_info = {
                    "first_name": contact.get("forename", ""),
                    "last_name": contact.get("name", ""),
                    "email": corporation.get("email", ""),
                    "company": corporation.get("name", ""),
                    "phone": corporation.get("mobile", "")
                }
                
                # Vérification des données importantes
                if not customer_info["email"] or not customer_info["first_name"]:
                    log_activity(f"❌ Informations client incomplètes: email={customer_info['email']}, prénom={customer_info['first_name']}, nom={customer_info['last_name']}")
                    return None
                
                log_activity(f"✅ Informations client récupérées avec succès: {customer_info['first_name']} {customer_info['last_name']}")
                return customer_info
            else:
                log_activity(f"❌ Erreur API Sellsy lors de la récupération client: {result.get('error')}")
                return None
        else:
            log_activity(f"❌ Erreur HTTP Sellsy: {response.status_code}")
            log_activity(f"📄 Détail de la réponse: {response.text}")
            return None
    except Exception as e:
        log_activity(f"❌ Exception lors de la récupération client: {str(e)}")
        return None

# Envoie un email personnalisé via l'API Sellsy en utilisant le template email
def send_email_via_sellsy_template(client_id, customer_info, installer_name, gocardless_link, signature_date):
    log_activity(f"📤 Envoi de l'email via le template Sellsy à {customer_info['email']}...")
    
    # Utiliser un nonce unique avec millisecondes
    nonce = str(int(time.time() * 1000))
    
    # Tenter la conversion en entier pour l'ID client
    try:
        client_id_param = int(client_id)
    except ValueError:
        client_id_param = client_id
    
    # Variables à remplacer dans le template
    custom_vars = {
        "Installateur": installer_name,
        "lienGoCardless": gocardless_link,
        "Date de signature de contrat": signature_date
    }
    
    # Structure modifiée pour correspondre à vos besoins
    email_params = {
        "linkedtype": "third",
        "linkedid": client_id_param,
        "emails": [customer_info["email"]],
        "templateId": SELLSY_EMAIL_TEMPLATE_ID,
        "addsendertoemail": "N",  # Ne pas mettre l'expéditeur en copie
        "fromName": "SUNLIB",     # Nom d'expéditeur personnalisé
        "fromEmail": "abonne@sunlib.fr",  # Email d'expéditeur personnalisé
        "customvars": custom_vars  # Variables à remplacer dans le template
    }
    
    sellsy_request = {
        "method": "Mails.sendOne",
        "params": {
            "email": email_params
        }
    }
    
    log_activity(f"🔧 Paramètres requête email Sellsy: {json.dumps(sellsy_request)}")
    
    oauth_params = {
        "oauth_consumer_key": SELLSY_CONSUMER_TOKEN,
        "oauth_token": SELLSY_USER_TOKEN,
        "oauth_nonce": nonce,
        "oauth_timestamp": nonce,
        "oauth_signature_method": "PLAINTEXT",
        "oauth_version": "1.0",
        "oauth_signature": f"{SELLSY_CONSUMER_SECRET}&{SELLSY_USER_SECRET}",
        "io_mode": "json",
        "do_in": json.dumps(sellsy_request)
    }
    
    try:
        response = requests.post(SELLSY_API_URL, data=oauth_params)
        log_activity(f"📊 Code de réponse email Sellsy: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("status") == "success":
                log_activity(f"✅ Email envoyé avec succès à {customer_info['email']} via le template {SELLSY_EMAIL_TEMPLATE_ID}")
                return True
            else:
                log_activity(f"❌ Erreur API Sellsy lors de l'envoi email: {result.get('error')}")
                log_activity(f"📄 Détail de la réponse: {json.dumps(result)}")
                return False
        else:
            log_activity(f"❌ Erreur HTTP Sellsy: {response.status_code}")
            log_activity(f"📄 Détail de la réponse: {response.text}")
            return False
    except Exception as e:
        log_activity(f"❌ Exception lors de l'envoi email: {str(e)}")
        return False

# Processus pour gérer une demande de mandat
def process_mandate_request(client_id, record_id, installer_name, signature_date):
    log_activity(f"🔄 Traitement de la demande de mandat pour client {client_id}...")
    
    # 1. Récupérer les informations du client
    customer_info = get_customer_info_from_sellsy(client_id)
    if not customer_info:
        log_activity("❌ Impossible de poursuivre sans les informations du client")
        return
    
    # Vérification des informations du client
    if not customer_info["email"] or not customer_info["first_name"]:
        log_activity("❌ Informations client incomplètes (email ou nom manquant)")
        return
    
    # 2. Utiliser le lien GoCardless direct défini en haut du script
    if not GOCARDLESS_DIRECT_LINK:
        log_activity("❌ Lien GoCardless direct non disponible")
        return
    
    # Petit délai pour éviter les problèmes de rate limiting
    time.sleep(1)
    
    # 3. Envoyer l'email via le template Sellsy avec le lien direct
    email_sent = send_email_via_sellsy_template(
        client_id=client_id,
        customer_info=customer_info,
        installer_name=installer_name,
        gocardless_link=GOCARDLESS_DIRECT_LINK,
        signature_date=signature_date
    )
    
    if email_sent:
        # 4. Mettre à jour Airtable pour marquer l'email comme envoyé
        mark_email_sent_in_airtable(record_id)
    else:
        log_activity("❌ L'email n'a pas pu être envoyé, la mise à jour Airtable n'est pas effectuée")

# Marque la case "Email Mandat sellsy" dans Airtable
def mark_email_sent_in_airtable(record_id):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    log_activity(f"🔄 Mise à jour de l'enregistrement Airtable {record_id}...")
    
    # Mettre à jour uniquement les champs qui existent dans Airtable
    data = {
        "fields": {
            "Email Mandat sellsy": True,  # Assurez-vous que le nom du champ est exact
            "Date envoi mandat": datetime.now().strftime("%Y-%m-%d")
        }
    }
    
    log_activity(f"📝 Données pour la mise à jour: {json.dumps(data)}")
    
    response = requests.patch(f"{AIRTABLE_API_URL}/{record_id}", headers=headers, json=data)
    if response.status_code == 200:
        log_activity("✅ Champ 'Email Mandat sellsy' mis à jour dans Airtable.")
        # Afficher les détails de la réponse pour vérifier
        log_activity(f"📄 Détail de la réponse Airtable: {json.dumps(response.json())}")
    else:
        log_activity(f"❌ Erreur mise à jour Airtable : {response.status_code} - {response.text}")

# Fonction de vérification des configurations API
def check_api_configurations():
    log_activity("🔍 Vérification des configurations API...")
    
    config_ok = True
    
    # Vérification Airtable
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_NAME:
        log_activity("❌ Configuration Airtable incomplète")
        config_ok = False
    
    # Vérification de la base des installateurs
    if not AIRTABLE_INSTALLERS_BASE_ID:
        log_activity("⚠️ Configuration base des installateurs manquante (AIRTABLE_INSTALLERS_BASE_ID)")
        log_activity("⚠️ Les noms d'installateurs ne seront pas récupérés correctement")
    
    # Vérification Sellsy
    if not SELLSY_CONSUMER_TOKEN or not SELLSY_CONSUMER_SECRET or not SELLSY_USER_TOKEN or not SELLSY_USER_SECRET:
        log_activity("❌ Configuration Sellsy incomplète")
        config_ok = False
    
    if config_ok:
        log_activity("✅ Toutes les configurations API sont présentes")
    else:
        # Afficher des valeurs masquées pour aider au débogage
        log_activity(f"AIRTABLE_API_KEY: {'Défini' if AIRTABLE_API_KEY else 'Non défini'}")
        log_activity(f"AIRTABLE_INSTALLERS_BASE_ID: {'Défini' if AIRTABLE_INSTALLERS_BASE_ID else 'Non défini'}")
        log_activity(f"SELLSY_CONSUMER_TOKEN: {'Défini' if SELLSY_CONSUMER_TOKEN else 'Non défini'}")
        log_activity(f"SELLSY_USER_TOKEN: {'Défini' if SELLSY_USER_TOKEN else 'Non défini'}")
    
    return config_ok

# Test de connexion aux APIs
def test_api_connections():
    log_activity("🧪 Test des connexions API...")
    
    # Test Airtable
    try:
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get(AIRTABLE_API_URL, headers=headers, params={"maxRecords": 1})
        if response.status_code == 200:
            log_activity("✅ Connexion à Airtable réussie")
        else:
            log_activity(f"❌ Échec connexion Airtable: {response.status_code} - {response.text}")
    except Exception as e:
        log_activity(f"❌ Exception test Airtable: {str(e)}")
    
    # Test Airtable Table des installateurs
    try:
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.get(AIRTABLE_INSTALLERS_API_URL, headers=headers, params={"maxRecords": 1})
        if response.status_code == 200:
            log_activity(f"✅ Connexion à la table Airtable '{AIRTABLE_INSTALLATEURS_TABLE}' réussie")
        else:
            log_activity(f"⚠️ Échec connexion à la table '{AIRTABLE_INSTALLATEURS_TABLE}': {response.status_code} - {response.text}")
    except Exception as e:
        log_activity(f"⚠️ Exception test Airtable Installateurs: {str(e)}")
    
    # Test Sellsy - Récupération liste de clients
    try:
        # Utiliser un nonce unique avec millisecondes
        nonce = str(int(time.time() * 1000))
        sellsy_request = {
            "method": "Client.getList",
            "params": {
                "pagination": {"nbperpage": 1}
            }
        }
        oauth_params = {
            "oauth_consumer_key": SELLSY_CONSUMER_TOKEN,
            "oauth_token": SELLSY_USER_TOKEN,
            "oauth_nonce": nonce,
            "oauth_timestamp": nonce,
            "oauth_signature_method": "PLAINTEXT",
            "oauth_version": "1.0",
            "oauth_signature": f"{SELLSY_CONSUMER_SECRET}&{SELLSY_USER_SECRET}",
            "io_mode": "json",
            "do_in": json.dumps(sellsy_request)
        }
        response = requests.post(SELLSY_API_URL, data=oauth_params)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                log_activity("✅ Connexion à Sellsy réussie")
            else:
                log_activity(f"❌ Échec API Sellsy: {result.get('error')}")
        else:
            log_activity(f"❌ Échec connexion Sellsy: {response.status_code} - {response.text}")
    except Exception as e:
        log_activity(f"❌ Exception test Sellsy: {str(e)}")

# Fonction principale
def main():
    log_activity("🚀 Lancement de la surveillance Airtable...")
    
    # Vérifier les configurations
    if not check_api_configurations():
        log_activity("⚠️ Certaines configurations sont manquantes, le programme pourrait ne pas fonctionner correctement")
    
    # Tester les connexions API avant de commencer
    test_api_connections()
    
    # Si exécuté dans GitHub Actions, faire une seule vérification
    if os.getenv("GITHUB_ACTIONS"):
        log_activity("🔍 Exécution unique dans GitHub Actions")
        check_airtable_changes()
    else:
        # Boucle continue pour exécution locale
        try:
            while True:
                check_airtable_changes()
                log_activity(f"🕒 Attente {CHECK_INTERVAL} secondes avant le prochain check.")
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            log_activity("🛑 Surveillance interrompue par l'utilisateur.")

if __name__ == "__main__":
    main()

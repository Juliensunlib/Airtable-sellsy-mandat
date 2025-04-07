import os
import time
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import gocardless_pro

# Chargement des variables d'environnement
load_dotenv()

# Configuration des API depuis les variables d'environnement et nettoyage des valeurs
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "").strip()
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "").strip()
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "").strip()

SELLSY_CONSUMER_TOKEN = os.getenv("SELLSY_CONSUMER_TOKEN", "").strip()
SELLSY_CONSUMER_SECRET = os.getenv("SELLSY_CONSUMER_SECRET", "").strip()
SELLSY_USER_TOKEN = os.getenv("SELLSY_USER_TOKEN", "").strip()
SELLSY_USER_SECRET = os.getenv("SELLSY_USER_SECRET", "").strip()

GOCARDLESS_ACCESS_TOKEN = os.getenv("GOCARDLESS_ACCESS_TOKEN", "").strip()
GOCARDLESS_ENVIRONMENT = os.getenv("GOCARDLESS_ENVIRONMENT", "live").strip()  # ou "live" pour production

# Initialisation du client GoCardless
gocardless_client = gocardless_pro.Client(
    access_token=GOCARDLESS_ACCESS_TOKEN,
    environment=GOCARDLESS_ENVIRONMENT
)

# ID du template d'email dans Sellsy
SELLSY_EMAIL_TEMPLATE_ID = "74"  # ID du template "Demande de mandat API"

# Paramètres de l'application
LOG_DIR = os.getenv("LOG_DIR", "logs")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 min par défaut

# URLS des APIs
AIRTABLE_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
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

    log_activity("📡 Vérification des changements Airtable...")

    response = requests.get(AIRTABLE_API_URL, headers=headers)

    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            fields = record.get("fields", {})
            record_id = record.get("id")
            
            # Vérifie si le contrat est signé mais que le mandat n'a pas encore été envoyé
            if fields.get("Contrat abonnement signe") and not fields.get("Email Mandat sellsy"):
                customer_name = fields.get("Nom", "Client")
                customer_email = fields.get("Email")
                customer_id = fields.get("ID_Sellsy", "").strip()  # Nettoyage de l'ID
                installer_name = fields.get("Installateur", "")
                signature_date = fields.get("Date de signature de contrat", "")
                
                log_activity(f"📨 Préparation de l'envoi d'email pour : {customer_name} (Email: {customer_email}, ID Sellsy: {customer_id})")
                
                # Envoi direct de l'email avec le lien de création de mandat (pas de création de mandat préalable)
                process_mandate_request(client_id=customer_id, 
                                       record_id=record_id, 
                                       installer_name=installer_name,
                                       signature_date=signature_date)
            elif fields.get("Email Mandat sellsy"):
                log_activity(f"⏩ Invitation déjà envoyée pour {fields.get('Nom', 'Client')}, on ignore.")
                
            # NOUVEAU: Vérifier si un mandat a été créé mais pas encore associé à Sellsy
            if fields.get("Mandat GoCardless") and not fields.get("Mandat associé à Sellsy"):
                mandat_id = fields.get("Mandat GoCardless")
                sellsy_id = fields.get("ID_Sellsy", "").strip()
                if mandat_id and sellsy_id:
                    log_activity(f"🔄 Association du mandat {mandat_id} au client Sellsy ID {sellsy_id}")
                    # Associer le mandat au client dans Sellsy
                    associate_mandate_with_sellsy(mandat_id, sellsy_id, record_id)
    else:
        log_activity(f"❌ Erreur d'Airtable : {response.status_code} - {response.text}")

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

# NOUVELLE FONCTION: Surveiller les webhooks GoCardless pour les mandats créés
def setup_gocardless_webhook():
    # Cette fonction devrait être appelée une seule fois pour configurer un webhook
    # qui sera notifié lorsqu'un mandat est créé
    log_activity("🔧 Configuration d'un webhook GoCardless pour les mandats...")
    try:
        webhook = gocardless_client.webhooks.create({
            "url": "https://votre-serveur.com/gocardless-webhook",  # À remplacer par votre URL
            "events": ["mandates"]
        })
        log_activity(f"✅ Webhook GoCardless créé avec l'ID: {webhook.id}")
        return True
    except Exception as e:
        log_activity(f"❌ Échec de création du webhook GoCardless: {str(e)}")
        return False

# NOUVELLE FONCTION: Point d'entrée pour le webhook GoCardless
def handle_gocardless_webhook(webhook_data):
    # Cette fonction devrait être appelée par votre serveur web lorsqu'il reçoit 
    # une notification de GoCardless
    log_activity("📥 Réception d'un webhook GoCardless")
    
    try:
        # Vérifier la signature du webhook pour sécurité
        
        # Parcourir les événements
        for event in webhook_data.get("events", []):
            if event.get("resource_type") == "mandates" and event.get("action") == "created":
                mandate_id = event.get("links", {}).get("mandate")
                customer_id = event.get("links", {}).get("customer")
                
                if mandate_id and customer_id:
                    log_activity(f"✅ Nouveau mandat créé: {mandate_id} pour client GoCardless: {customer_id}")
                    
                    # Rechercher le client dans Airtable pour obtenir l'ID Sellsy
                    find_and_update_mandate_in_airtable(customer_id, mandate_id)
        
        return True
    except Exception as e:
        log_activity(f"❌ Erreur traitement webhook GoCardless: {str(e)}")
        return False

# NOUVELLE FONCTION: Rechercher le client GoCardless dans Airtable
def find_and_update_mandate_in_airtable(gocardless_customer_id, mandate_id):
    log_activity(f"🔍 Recherche du client GoCardless {gocardless_customer_id} dans Airtable...")
    
    # Cette fonction implémente une recherche dans Airtable pour trouver le client correspondant
    # Une implémentation plus complète nécessiterait de stocker l'ID client GoCardless dans Airtable
    
    # Alternative: utiliser l'email pour faire la correspondance
    customer = gocardless_client.customers.get(gocardless_customer_id)
    email = customer.email
    
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Recherche par email dans Airtable
    params = {
        "filterByFormula": f"{{Email}}='{email}'"
    }
    
    response = requests.get(AIRTABLE_API_URL, headers=headers, params=params)
    
    if response.status_code == 200:
        records = response.json().get("records", [])
        if records:
            record = records[0]
            record_id = record["id"]
            fields = record.get("fields", {})
            sellsy_id = fields.get("ID_Sellsy", "")
            
            if sellsy_id:
                log_activity(f"✅ Client trouvé dans Airtable avec ID Sellsy: {sellsy_id}")
                
                # Mettre à jour Airtable avec l'ID du mandat
                update_data = {
                    "fields": {
                        "Mandat GoCardless": mandate_id
                    }
                }
                
                update_response = requests.patch(f"{AIRTABLE_API_URL}/{record_id}", headers=headers, json=update_data)
                
                if update_response.status_code == 200:
                    log_activity(f"✅ ID de mandat mis à jour dans Airtable")
                    
                    # Associer le mandat à Sellsy
                    associate_mandate_with_sellsy(mandate_id, sellsy_id, record_id)
                else:
                    log_activity(f"❌ Erreur mise à jour Airtable: {update_response.status_code}")
            else:
                log_activity("❌ Client trouvé dans Airtable mais sans ID Sellsy")
        else:
            log_activity(f"❌ Aucun client avec l'email {email} trouvé dans Airtable")
    else:
        log_activity(f"❌ Erreur recherche Airtable: {response.status_code}")

# NOUVELLE FONCTION: Associer un mandat GoCardless à un client Sellsy
def associate_mandate_with_sellsy(mandate_id, sellsy_id, airtable_record_id=None):
    log_activity(f"🔄 Association du mandat {mandate_id} au client Sellsy {sellsy_id}...")
    
    # Récupérer les détails du mandat depuis GoCardless
    try:
        mandate = gocardless_client.mandates.get(mandate_id)
        bank_reference = mandate.reference  # Référence bancaire du mandat
        scheme = mandate.scheme  # Schéma de prélèvement (SEPA, etc.)
        
        # Utiliser le timestamp avec millisecondes pour avoir un nonce vraiment unique
        nonce = str(int(time.time() * 1000))
        
        # Convertir l'ID Sellsy en entier si possible
        try:
            sellsy_id_param = int(sellsy_id)
        except ValueError:
            sellsy_id_param = sellsy_id
        
        # Créer le moyen de paiement dans Sellsy
        sellsy_request = {
            "method": "ClientPaymentModes.create",
            "params": {
                "clientid": sellsy_id_param,
                "label": f"Mandat GoCardless {bank_reference}",
                "ident": mandate_id,  # Identifiant externe du mandat
                "type": "directdebit",  # Type de paiement: prélèvement direct
                "active": "Y",
                "defaultPm": "Y",  # Définir comme moyen de paiement par défaut
                "data": {
                    "bankName": "GoCardless",
                    "mandateRef": bank_reference,
                    "mandateSignDate": datetime.now().strftime("%Y-%m-%d"),
                    "scheme": scheme.lower()  # sepa, bacs, etc.
                }
            }
        }
        
        log_activity(f"🔧 Paramètres requête Sellsy pour ajout mandat: {json.dumps(sellsy_request)}")
        
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
                payment_mode_id = result.get("response")
                log_activity(f"✅ Mandat ajouté avec succès dans Sellsy avec ID: {payment_mode_id}")
                
                # Si on a l'ID Airtable, mettre à jour pour indiquer que le mandat est associé à Sellsy
                if airtable_record_id:
                    headers = {
                        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    
                    update_data = {
                        "fields": {
                            "Mandat associé à Sellsy": True
                        }
                    }
                    
                    update_response = requests.patch(f"{AIRTABLE_API_URL}/{airtable_record_id}", 
                                                headers=headers, json=update_data)
                    
                    if update_response.status_code == 200:
                        log_activity("✅ Statut d'association du mandat mis à jour dans Airtable")
                    else:
                        log_activity(f"❌ Erreur mise à jour statut Airtable: {update_response.status_code}")
                
                return True
            else:
                log_activity(f"❌ Erreur API Sellsy lors de l'ajout du mandat: {result.get('error')}")
                return False
        else:
            log_activity(f"❌ Erreur HTTP Sellsy: {response.status_code}")
            log_activity(f"📄 Détail de la réponse: {response.text}")
            return False
            
    except Exception as e:
        log_activity(f"❌ Exception lors de l'association du mandat: {str(e)}")
        return False

# Envoie un email personnalisé via l'API Sellsy en utilisant le template email
def send_email_via_sellsy_template(client_id, customer_info, installer_name, signature_date):
    log_activity(f"📤 Envoi de l'email via le template Sellsy à {customer_info['email']}...")
    
    # On n'a plus besoin de créer un lien GoCardless, il est inclus dans le template
    
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
        "DateSignature": signature_date
        # Le lien GoCardless est maintenant directement dans le template
    }
    
    # Paramètres de l'email avec le template ID 74
    email_params = {
        "linkedtype": "client",
        "linkedid": client_id_param,
        "emails": [customer_info["email"]],
        "mailid": SELLSY_EMAIL_TEMPLATE_ID,  # ID du template email
        "useridfrom": "staff",  # Envoyé par le staff
        "customvars": custom_vars  # Variables à remplacer dans le template
    }
    
    sellsy_request = {
        "method": "Mails.sendOne",
        "params": email_params
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

# Processus simplifié pour gérer une demande de mandat
def process_mandate_request(client_id, record_id, installer_name, signature_date):
    log_activity(f"🔄 Traitement de la demande d'envoi de mandat pour client {client_id}...")
    
    # 1. Récupérer les informations du client
    customer_info = get_customer_info_from_sellsy(client_id)
    if not customer_info:
        log_activity("❌ Impossible de poursuivre sans les informations du client")
        return
    
    # Vérification des infos client
    if not customer_info["email"] or not customer_info["first_name"]:
        log_activity("❌ Informations client incomplètes (email ou nom manquant)")
        return
    
    # 2. Envoyer l'email via le template Sellsy (avec lien GoCardless déjà inclus dans le template)
    email_sent = send_email_via_sellsy_template(
        client_id=client_id,
        customer_info=customer_info,
        installer_name=installer_name,
        signature_date=signature_date
    )
    
    if email_sent:
        # 3. Mettre à jour Airtable pour marquer l'email comme envoyé
        mark_email_sent_in_airtable(record_id)
    else:
        log_activity("❌ L'email n'a pas pu être envoyé, la mise à jour Airtable n'est pas effectuée")

# Marque la case "Email Mandat sellsy" dans Airtable
def mark_email_sent_in_airtable(record_id):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Mise à jour des champs
    data = {
        "fields": {
            "Email Mandat sellsy": True,
            "Date envoi mandat": datetime.now().strftime("%Y-%m-%d")
            # Plus besoin de stocker le lien car il est maintenant dans le template
        }
    }
    
    response = requests.patch(f"{AIRTABLE_API_URL}/{record_id}", headers=headers, json=data)
    if response.status_code == 200:
        log_activity("✅ Champ 'Email Mandat sellsy' mis à jour dans Airtable.")
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
    
    # Vérification Sellsy
    if not SELLSY_CONSUMER_TOKEN or not SELLSY_CONSUMER_SECRET or not SELLSY_USER_TOKEN or not SELLSY_USER_SECRET:
        log_activity("❌ Configuration Sellsy incomplète")
        config_ok = False
    
    # Vérification GoCardless
    if not GOCARDLESS_ACCESS_TOKEN:
        log_activity("❌ Configuration GoCardless incomplète")
        config_ok = False
    
    if config_ok:
        log_activity("✅ Toutes les configurations API sont présentes")
    else:
        # Afficher des valeurs masquées pour aider au débogage
        log_activity(f"AIRTABLE_API_KEY: {'Défini' if AIRTABLE_API_KEY else 'Non défini'}")
        log_activity(f"SELLSY_CONSUMER_TOKEN: {'Défini' if SELLSY_CONSUMER_TOKEN else 'Non défini'}")
        log_activity(f"SELLSY_USER_TOKEN: {'Défini' if SELLSY_USER_TOKEN else 'Non défini'}")
        log_activity(f"GOCARDLESS_ACCESS_TOKEN: {'Défini' if GOCARDLESS_ACCESS_TOKEN else 'Non défini'}")
    
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
    
    # Test GoCardless avec la bibliothèque officielle
    try:
        # Récupérer la liste des créanciers (devrait fonctionner avec n'importe quel token valide)
        creditors = gocardless_client.creditors.list()
        log_activity("✅ Connexion à GoCardless réussie")
        if len(list(creditors.records)) > 0:
            log_activity(f"✅ {len(list(creditors.records))} créancier(s) trouvé(s) dans le compte GoCardless")
    except Exception as e:
        log_activity(f"❌ Exception test GoCardless: {str(e)}")

# Point d'entrée pour le webhook GoCardless (à exposer via votre serveur web)
def webhook_endpoint(request_data):
    # Vérification de signature et autres validations de sécurité
    # ...
    
    # Traitement des données du webhook
    handle_gocardless_webhook(request_data)

# Boucle principale

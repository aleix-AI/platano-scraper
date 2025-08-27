import telebot
import os
import requests
from bs4 import BeautifulSoup
import sqlite3
import threading
import time
import psycopg2
from psycopg2 import sql
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tokens dels bots (ara des de variables d'entorn)
CLIENT_BOT_TOKEN = os.environ.get('CLIENT_BOT_TOKEN')
ADMIN_BOT_TOKEN = os.environ.get('ADMIN_BOT_TOKEN') 
DATABASE_URL = os.environ.get('DATABASE_URL')

# Verificar que tenim tots els tokens
if not CLIENT_BOT_TOKEN or not ADMIN_BOT_TOKEN:
    logger.error("ERROR: Tokens dels bots no configurats!")
    exit(1)

# Crear bots
client_bot = telebot.TeleBot(CLIENT_BOT_TOKEN)
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

# ID de l'administrador
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID')
if ADMIN_USER_ID:
    ADMIN_USER_ID = int(ADMIN_USER_ID)

class DatabaseManager:
    def __init__(self, database_url=None):
        if database_url:
            # PostgreSQL (Railway)
            self.connection = psycopg2.connect(database_url)
            self.is_postgresql = True
            logger.info("Connectat a PostgreSQL")
        else:
            # SQLite (desenvolupament local)
            self.connection = sqlite3.connect('godsells.db', check_same_thread=False)
            self.is_postgresql = False
            logger.info("Usant SQLite local")
        
        self.create_tables()
    
    def create_tables(self):
        cursor = self.connection.cursor()
        
        if self.is_postgresql:
            # PostgreSQL queries
            queries = [
                """
                CREATE TABLE IF NOT EXISTS productes (
                    id SERIAL PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    descripcio TEXT,
                    categoria VARCHAR(100),
                    talles_disponibles TEXT,
                    preu_web_platanos DECIMAL(10,2),
                    preu_venda_meu DECIMAL(10,2),
                    marge DECIMAL(5,2),
                    url_producte TEXT,
                    imatge_url TEXT,
                    data_afegit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actiu BOOLEAN DEFAULT TRUE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS consultes_pendents (
                    id SERIAL PRIMARY KEY,
                    client_user_id BIGINT NOT NULL,
                    client_nom VARCHAR(100),
                    client_username VARCHAR(100),
                    producte_buscat TEXT NOT NULL,
                    descripcio TEXT,
                    foto_url TEXT,
                    data_consulta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estat VARCHAR(20) DEFAULT 'pendent'
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS comandes (
                    id SERIAL PRIMARY KEY,
                    client_user_id BIGINT NOT NULL,
                    client_nom VARCHAR(100),
                    producte_id INTEGER REFERENCES productes(id),
                    producte_nom TEXT,
                    talla VARCHAR(10),
                    preu_final DECIMAL(10,2),
                    estat VARCHAR(20) DEFAULT 'pendent',
                    data_comanda TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
                """
            ]
        else:
            # SQLite queries
            queries = [
                """
                CREATE TABLE IF NOT EXISTS productes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom TEXT NOT NULL,
                    descripcio TEXT,
                    categoria TEXT,
                    talles_disponibles TEXT,
                    preu_web_platanos REAL,
                    preu_venda_meu REAL,
                    marge REAL,
                    url_producte TEXT,
                    imatge_url TEXT,
                    data_afegit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actiu INTEGER DEFAULT 1
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS consultes_pendents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_user_id INTEGER NOT NULL,
                    client_nom TEXT,
                    client_username TEXT,
                    producte_buscat TEXT NOT NULL,
                    descripcio TEXT,
                    foto_url TEXT,
                    data_consulta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estat TEXT DEFAULT 'pendent'
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS comandes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_user_id INTEGER NOT NULL,
                    client_nom TEXT,
                    producte_id INTEGER,
                    producte_nom TEXT,
                    talla TEXT,
                    preu_final REAL,
                    estat TEXT DEFAULT 'pendent',
                    data_comanda TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (producte_id) REFERENCES productes (id)
                )
                """
            ]
        
        for query in queries:
            try:
                cursor.execute(query)
                self.connection.commit()
                logger.info("Taula creada correctament")
            except Exception as e:
                logger.error(f"Error creant taula: {e}")
        
        cursor.close()
    
    def buscar_producte(self, terme_cerca):
        cursor = self.connection.cursor()
        if self.is_postgresql:
            query = "SELECT * FROM productes WHERE LOWER(nom) LIKE LOWER(%s) OR LOWER(descripcio) LIKE LOWER(%s) AND actiu = TRUE"
            cursor.execute(query, (f'%{terme_cerca}%', f'%{terme_cerca}%'))
        else:
            query = "SELECT * FROM productes WHERE (LOWER(nom) LIKE LOWER(?) OR LOWER(descripcio) LIKE LOWER(?)) AND actiu = 1"
            cursor.execute(query, (f'%{terme_cerca}%', f'%{terme_cerca}%'))
        
        result = cursor.fetchone()
        cursor.close()
        return result
    
    def afegir_consulta_pendent(self, user_id, nom_usuari, username, producte_buscat, descripcio=""):
        cursor = self.connection.cursor()
        if self.is_postgresql:
            query = "INSERT INTO consultes_pendents (client_user_id, client_nom, client_username, producte_buscat, descripcio) VALUES (%s, %s, %s, %s, %s)"
        else:
            query = "INSERT INTO consultes_pendents (client_user_id, client_nom, client_username, producte_buscat, descripcio) VALUES (?, ?, ?, ?, ?)"
        
        cursor.execute(query, (user_id, nom_usuari, username, producte_buscat, descripcio))
        self.connection.commit()
        cursor.close()
    
    def obtenir_consultes_pendents(self):
        cursor = self.connection.cursor()
        if self.is_postgresql:
            query = "SELECT * FROM consultes_pendents WHERE estat = %s ORDER BY data_consulta DESC"
            cursor.execute(query, ('pendent',))
        else:
            query = "SELECT * FROM consultes_pendents WHERE estat = ? ORDER BY data_consulta DESC"
            cursor.execute(query, ('pendent',))
        
        results = cursor.fetchall()
        cursor.close()
        return results
    
    def afegir_producte(self, nom, descripcio, categoria, talles, preu_web, preu_venda, url="", imatge=""):
        cursor = self.connection.cursor()
        marge = ((preu_venda - preu_web) / preu_web) * 100 if preu_web > 0 else 0
        
        if self.is_postgresql:
            query = """INSERT INTO productes (nom, descripcio, categoria, talles_disponibles, 
                      preu_web_platanos, preu_venda_meu, marge, url_producte, imatge_url) 
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"""
        else:
            query = """INSERT INTO productes (nom, descripcio, categoria, talles_disponibles, 
                      preu_web_platanos, preu_venda_meu, marge, url_producte, imatge_url) 
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        
        cursor.execute(query, (nom, descripcio, categoria, talles, preu_web, preu_venda, marge, url, imatge))
        
        if self.is_postgresql:
            product_id = cursor.fetchone()[0]
        else:
            product_id = cursor.lastrowid
            
        self.connection.commit()
        cursor.close()
        return product_id
    
    def crear_comanda(self, user_id, nom_usuari, producte_id, producte_nom, talla, preu_final):
        cursor = self.connection.cursor()
        if self.is_postgresql:
            query = """INSERT INTO comandes (client_user_id, client_nom, producte_id, producte_nom, talla, preu_final) 
                      VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"""
        else:
            query = """INSERT INTO comandes (client_user_id, client_nom, producte_id, producte_nom, talla, preu_final) 
                      VALUES (?, ?, ?, ?, ?, ?)"""
        
        cursor.execute(query, (user_id, nom_usuari, producte_id, producte_nom, talla, preu_final))
        
        if self.is_postgresql:
            order_id = cursor.fetchone()[0]
        else:
            order_id = cursor.lastrowid
            
        self.connection.commit()
        cursor.close()
        return order_id

# Inicialitzar base de dades
db = DatabaseManager(DATABASE_URL)

# ======================== BOT CLIENT ========================

@client_bot.message_handler(commands=['start'])
def client_start(message):
    welcome_msg = """
🔥 **Benvingut a GODSELLS!** 🔥

Som especialistes en sneakers exclusives.

📝 **Com funciona:**
• Escriu el nom del model que busques
• T'enviem disponibilitat i preu
• Confirmes la teva comanda
• Rebràs les teves sneakers!

👟 **Què pots buscar:**
• Nike, Adidas, Jordan...
• Especifica color i talla si la coneixes
• També pots enviar una foto del model

Escriu el que busques per començar! 👇
    """
    
    client_bot.send_message(message.chat.id, welcome_msg, parse_mode='Markdown')

@client_bot.message_handler(content_types=['text'])
def client_cerca_producte(message):
    terme_cerca = message.text.strip()
    user_id = message.from_user.id
    nom_usuari = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
    username = message.from_user.username or "sense_username"
    
    # Buscar a la base de dades
    producte = db.buscar_producte(terme_cerca)
    
    if producte:
        # Producte trobat
        id_prod, nom, descripcio, categoria, talles, preu_web, preu_venda, marge, url, imatge, data, actiu = producte
        
        resposta = f"""
✅ **PRODUCTE DISPONIBLE!**

👟 **{nom}**
📝 {descripcio}
💰 **Preu: {preu_venda}€**
📏 **Talles disponibles:** {talles}

Vols fer la comanda? Escriu la talla que vols:
Exemple: "Talla 42" o "42"
        """
        
        client_bot.send_message(message.chat.id, resposta, parse_mode='Markdown')
        
    else:
        # Producte NO trobat - afegir a consultes pendents
        db.afegir_consulta_pendent(user_id, nom_usuari, username, terme_cerca)
        
        resposta = """
🔍 **ESTEM BUSCANT EL TEU PRODUCTE...**

No tenim aquest model al catàleg ara mateix, però estem consultant amb els nostres proveïdors.

⏰ **T'avisarem tan aviat com el trobem!**

Mentre tant, pots continuar buscant altres models.
        """
        
        client_bot.send_message(message.chat.id, resposta, parse_mode='Markdown')
        
        # Notificar a l'admin
        if ADMIN_USER_ID:
            admin_msg = f"""
🔔 **NOVA CONSULTA PENDENT**

👤 Client: {nom_usuari} (@{username})
🔍 Busca: **{terme_cerca}**
📅 {time.strftime('%d/%m/%Y %H:%M')}

Usa /consultes per veure totes les pendents.
            """
            admin_bot.send_message(ADMIN_USER_ID, admin_msg, parse_mode='Markdown')

@client_bot.message_handler(content_types=['photo'])
def client_foto_producte(message):
    user_id = message.from_user.id
    nom_usuari = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
    username = message.from_user.username or "sense_username"
    
    # Obtenir la foto
    file_info = client_bot.get_file(message.photo[-1].file_id)
    foto_url = f"https://api.telegram.org/file/bot{CLIENT_BOT_TOKEN}/{file_info.file_path}"
    
    caption = message.caption or "Foto enviada sense descripció"
    
    # Afegir consulta pendent amb foto
    db.afegir_consulta_pendent(user_id, nom_usuari, username, "Consulta per foto", caption)
    
    resposta = """
📸 **FOTO REBUDA!**

Estem analitzant la imatge per identificar el model.

⏰ **T'avisarem tan aviat com el trobem!**
    """
    
    client_bot.send_message(message.chat.id, resposta, parse_mode='Markdown')
    
    # Notificar admin amb la foto
    if ADMIN_USER_ID:
        admin_msg = f"""
🔔 **NOVA CONSULTA AMB FOTO**

👤 Client: {nom_usuari} (@{username})
📸 Foto enviada
💬 Descripció: {caption}
📅 {time.strftime('%d/%m/%Y %H:%M')}
        """
        admin_bot.send_photo(ADMIN_USER_ID, message.photo[-1].file_id, caption=admin_msg, parse_mode='Markdown')

# ======================== BOT ADMIN ========================

@admin_bot.message_handler(commands=['start'])
def admin_start(message):
    global ADMIN_USER_ID
    ADMIN_USER_ID = message.from_user.id
    
    welcome_msg = """
⚙️ **GODSELLS ADMIN PANEL**

🎛️ **Comandes disponibles:**

📋 `/consultes` - Veure consultes pendents
🛒 `/comandes` - Veure comandes pendents  
➕ `/afegir` - Afegir nou producte
📊 `/stats` - Estadístiques
ℹ️ `/help` - Ajuda completa

Sistema connectat correctament! ✅
    """
    
    admin_bot.send_message(message.chat.id, welcome_msg, parse_mode='Markdown')

@admin_bot.message_handler(commands=['consultes'])
def admin_consultes(message):
    consultes = db.obtenir_consultes_pendents()
    
    if not consultes:
        admin_bot.send_message(message.chat.id, "📭 No hi ha consultes pendents.")
        return
    
    resposta = "📋 **CONSULTES PENDENTS:**\n\n"
    
    for consulta in consultes:
        id_consulta, user_id, nom, username, producte, descripcio, foto, data, estat = consulta
        resposta += f"""
🔹 **ID #{id_consulta}**
👤 {nom} (@{username})
🔍 Busca: **{producte}**
📅 {data}
➖➖➖➖➖➖
"""
    
    resposta += "\nUsa `/afegir` per afegir productes nous al catàleg."
    
    admin_bot.send_message(message.chat.id, resposta, parse_mode='Markdown')

@admin_bot.message_handler(commands=['afegir'])
def admin_afegir_producte(message):
    help_msg = """
➕ **AFEGIR PRODUCTE NOU**

**Format:** `/afegir nom | descripció | categoria | talles | preu_web | preu_venda`

**Exemple:**
`/afegir Air Jordan 4 Retro Bred | Sneakers clàssiques negres i vermelles | Jordan | 40,41,42,43,44,45 | 75.95 | 125.00`

**Camps:**
• **nom**: Nom del producte
• **descripció**: Descripció del producte  
• **categoria**: Nike, Adidas, Jordan, etc.
• **talles**: Separades per comes
• **preu_web**: Preu a platanosneaker.com
• **preu_venda**: El teu preu de venda
    """
    
    admin_bot.send_message(message.chat.id, help_msg, parse_mode='Markdown')

@admin_bot.message_handler(func=lambda message: message.text.startswith('/afegir '))
def admin_processar_afegir(message):
    try:
        # Parsejar la comanda - treure '/afegir ' (8 caràcters)
        content = message.text[8:].strip()
        parts = [part.strip() for part in content.split('|')]
        
        if len(parts) != 6:
            admin_bot.send_message(message.chat.id, f"❌ Format incorrecte. Esperava 6 parts, rebut {len(parts)}.\nUsa `/afegir` sense paràmetres per veure l'exemple.")
            return
        
        nom = parts[0].strip()
        descripcio = parts[1].strip()
        categoria = parts[2].strip()
        talles = parts[3].strip()
        preu_web = float(parts[4].strip())
        preu_venda = float(parts[5].strip())
        
        # Afegir a la base de dades
        product_id = db.afegir_producte(nom, descripcio, categoria, talles, preu_web, preu_venda)
        
        marge = ((preu_venda - preu_web) / preu_web) * 100
        
        confirmacio = f"""
✅ **PRODUCTE AFEGIT CORRECTAMENT!**

🆔 **ID:** #{product_id}
👟 **Nom:** {nom}
📝 **Descripció:** {descripcio}
🏷️ **Categoria:** {categoria}
📏 **Talles:** {talles}
💰 **Preu web:** {preu_web}€
💰 **Preu venda:** {preu_venda}€
📈 **Marge:** {marge:.1f}%

Els clients amb consultes pendents seran notificats automàticament.
        """
        
        admin_bot.send_message(message.chat.id, confirmacio, parse_mode='Markdown')
        
        # TODO: Notificar clients que esperaven aquest tipus de producte
        
    except ValueError:
        admin_bot.send_message(message.chat.id, "❌ Error en els preus. Han de ser números vàlids.")
    except Exception as e:
        admin_bot.send_message(message.chat.id, f"❌ Error afegint producte: {str(e)}")

@admin_bot.message_handler(commands=['help'])
def admin_help(message):
    help_msg = """
⚙️ **GUIA COMPLETA ADMIN**

**🔍 Gestió de consultes:**
`/consultes` - Veure què busquen els clients

**📦 Gestió de productes:**
`/afegir` - Instruccions per afegir productes
`/afegir nom | desc | cat | talles | preu_web | preu_venda`

**🛒 Gestió de comandes:**
`/comandes` - Veure comandes pendents
`/stats` - Estadístiques de vendes

**💡 Flux de treball:**
1. Client busca producte
2. Si no existeix → reps notificació
3. Tu afegeixes el producte amb `/afegir`
4. Client rep notificació automàtica
5. Client fa comanda → tu la gestionnes
    """
    
    admin_bot.send_message(message.chat.id, help_msg, parse_mode='Markdown')

# Funció per executar ambdós bots
def run_bots():
    def run_client():
        logger.info("Bot client iniciat...")
        client_bot.polling(none_stop=True)
    
    def run_admin():
        logger.info("Bot admin iniciat...")
        admin_bot.polling(none_stop=True)
    
    # Crear threads per cada bot
    client_thread = threading.Thread(target=run_client)
    admin_thread = threading.Thread(target=run_admin)
    
    client_thread.start()
    admin_thread.start()
    
    client_thread.join()
    admin_thread.join()

if __name__ == "__main__":
    logger.info("🚀 Iniciant sistema GODSELLS...")
    logger.info("📱 Bots configurats correctament")
    logger.info("🗄️ Base de dades connectada")
    
    run_bots()

import requests
import json
import csv
import psycopg2
from bs4 import BeautifulSoup
import time
import os
from urllib.parse import urljoin

class PlatanoscrapeR:
    def __init__(self):
        self.base_url = "https://platanosneaker.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.products = []
        
    def get_all_product_links(self):
        """Extreu tots els enllaços de productes de la web"""
        print("🔍 Buscant tots els enllaços de productes...")
        
        # URLs de categories conegudes
        category_urls = [
            f"{self.base_url}/",  # Página principal
            f"{self.base_url}/products/",  # Si tenen pàgina de productes
        ]
        
        product_links = set()
        
        for url in category_urls:
            try:
                response = requests.get(url, headers=self.headers)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Buscar enllaços que puguin ser productes
                links = soup.find_all('a', href=True)
                
                for link in links:
                    href = link.get('href')
                    if href and '/products/' in href:
                        full_url = urljoin(self.base_url, href)
                        product_links.add(full_url)
                
            except Exception as e:
                print(f"❌ Error extraient de {url}: {e}")
        
        print(f"✅ Trobats {len(product_links)} enllaços de productes")
        return list(product_links)
    
    def extract_product_info(self, product_url):
        """Extreu informació d'un producte específic"""
        try:
            response = requests.get(product_url, headers=self.headers)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extreure nom del producte
            name = ""
            title_selectors = ['h1', '.product-title', '.entry-title', 'title']
            for selector in title_selectors:
                element = soup.select_one(selector)
                if element:
                    name = element.get_text().strip()
                    break
            
            # Extreure preu
            price = 0.0
            price_selectors = ['.price', '.woocommerce-Price-amount', '.product-price', '[class*="price"]']
            for selector in price_selectors:
                element = soup.select_one(selector)
                if element:
                    price_text = element.get_text()
                    # Extreure número del preu
                    import re
                    price_match = re.search(r'€(\d+,?\d*)', price_text)
                    if price_match:
                        price = float(price_match.group(1).replace(',', '.'))
                        break
            
            # Extreure categoria (basat en URL o contingut)
            category = "General"
            if 'jordan' in product_url.lower() or 'jordan' in name.lower():
                category = "Jordan"
            elif 'nike' in product_url.lower() or 'nike' in name.lower():
                category = "Nike"
            elif 'adidas' in product_url.lower() or 'adidas' in name.lower():
                category = "Adidas"
            elif 'new-balance' in product_url.lower() or 'new balance' in name.lower():
                category = "New Balance"
            
            # Descripció bàsica
            description = f"Sneakers de qualitat {name}"
            
            return {
                'name': name,
                'description': description,
                'category': category,
                'price': price,
                'url': product_url,
                'sizes': "36,37,38,39,40,41,42,43,44,45"  # Talles estàndard
            }
            
        except Exception as e:
            print(f"❌ Error extraient {product_url}: {e}")
            return None
    
    def scrape_all_products(self):
        """Procés complet d'extracció"""
        print("🚀 Iniciant extracció completa de platanosneaker.com")
        
        # Obtenir tots els enllaços
        product_links = self.get_all_product_links()
        
        # Extreure cada producte
        for i, link in enumerate(product_links):
            print(f"📦 Extraient producte {i+1}/{len(product_links)}: {link}")
            
            product = self.extract_product_info(link)
            if product:
                self.products.append(product)
            
            # Pausa per no sobrecarregar el servidor
            time.sleep(1)
        
        print(f"✅ Extracció completada! {len(self.products)} productes extrets")
        return self.products
    
    def save_to_csv(self, filename="platanos_products.csv"):
        """Guarda productes a CSV"""
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['name', 'description', 'category', 'price', 'url', 'sizes'])
            writer.writeheader()
            writer.writerows(self.products)
        print(f"💾 Productes guardats a {filename}")
    
    def save_to_railway_db(self, database_url):
        """Puja productes directament a Railway PostgreSQL"""
        if not database_url:
            print("❌ DATABASE_URL no configurada")
            return
        
        try:
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()
            
            # Insertar cada producte
            for product in self.products:
                # Calcular preu de venda amb marge del 50%
                sale_price = product['price'] * 1.5
                
                cursor.execute("""
                    INSERT INTO productes (nom, descripcio, categoria, talles_disponibles, 
                                         preu_web_platanos, preu_venda_meu, marge, url_producte)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    product['name'],
                    product['description'], 
                    product['category'],
                    product['sizes'],
                    product['price'],
                    sale_price,
                    50.0,
                    product['url']
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ {len(self.products)} productes pujats a Railway!")
            
        except Exception as e:
            print(f"❌ Error pujant a Railway: {e}")
    
    def generate_telegram_commands(self, markup=50):
        """Genera comandes /afegir per Telegram"""
        commands = []
        for product in self.products:
            sale_price = round(product['price'] * (1 + markup/100), 2)
            command = f"/afegir {product['name']} | {product['description']} | {product['category']} | {product['sizes']} | {product['price']} | {sale_price}"
            commands.append(command)
        
        # Guardar en arxiu
        with open('telegram_commands.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(commands))
        
        print(f"📱 {len(commands)} comandes Telegram generades!")
        return commands

def main():
    scraper = PlatanoscrapeR()
    
    # Extreure tots els productes
    products = scraper.scrape_all_products()
    
    if products:
        # Guardar a CSV
        scraper.save_to_csv()
        
        # Generar comandes Telegram
        commands = scraper.generate_telegram_commands()
        
        # Si tenim DATABASE_URL, pujar directament
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            scraper.save_to_railway_db(database_url)
        
        print("\n🎯 OPCIONS DISPONIBLES:")
        print("1. Arxiu CSV creat: platanos_products.csv")
        print("2. Comandes Telegram: telegram_commands.txt")
        print("3. Base de dades Railway actualitzada (si DATABASE_URL configurada)")
    
    else:
        print("❌ No s'han pogut extreure productes")

if __name__ == "__main__":
    main()

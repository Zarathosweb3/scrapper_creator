import time
import random
import json
import requests
from datetime import datetime, timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from telegram import Bot

class WebScraper:
    def __init__(self, telegram_token: str, channel_id: str):
        """
        Initialise le scraper avec Selenium et le bot Telegram.
        """
        self.telegram_token = telegram_token
        self.channel_id = channel_id

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        self.bot = Bot(token=self.telegram_token)

        prefs = {
            "profile.default_content_setting_values.clipboard": 1,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(options=chrome_options)
        self.last_token = ""

    def send_telegram_message(self, message: str):
        """
        Envoie un message sur Telegram avec parse_mode=HTML
        pour inclure des liens cliquables.
        """
        send_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": message,
            "parse_mode": "HTML"             # Permet d'utiliser <a href="...">...</a>

        }

        results = requests.post(send_url, data=payload)
        print(results.json())
        print("Message envoyé sur Telegram.")

    def click_element(self, by: By, identifier: str):
        """
        Clique sur un élément spécifique trouvé par un sélecteur, avec un temps d'attente réduit.
        """
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((by, identifier))
            )
            print(f"Clic sur l'élément : {identifier}")
            element.click()
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"Erreur lors du clic sur l'élément {identifier}: {e}")

    def close(self):
        """
        Ferme le navigateur Selenium.
        """
        self.driver.quit()

    def get_contract_creator_basescan(self, contract_address: str, api_key: str) -> str:
        """
        Récupère l'adresse du créateur du contrat (Blockchain Base).
        """
        url_req = (
            "https://api.basescan.org/api"
            "?module=contract"
            "&action=getcontractcreation"
            f"&contractaddresses={contract_address}"
            f"&apikey={api_key}"
        )
        results = requests.get(url_req)
        json_res = results.json()
        return json_res["result"][0]["contractCreator"]

    def get_wallet_age_in_hours(self, creator_address: str, api_key: str) -> float:
        """
        Récupère la première transaction du wallet (creator_address)
        et calcule depuis combien d'heures ce wallet existe.
        """
        txlist_url = (
            "https://api.basescan.org/api"
            "?module=account"
            "&action=txlist"
            f"&address={creator_address}"
            "&startblock=0&endblock=99999999"
            "&sort=asc"
            f"&apikey={api_key}"
        )
        try:
            resp = requests.get(txlist_url)
            data = resp.json()
            txs = data.get("result", [])
            if not txs:
                return 0.0

            first_tx = txs[0]
            timestamp_s = int(first_tx["timeStamp"])
            first_tx_dt = datetime.utcfromtimestamp(timestamp_s).replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)

            diff_seconds = (now_utc - first_tx_dt).total_seconds()
            diff_hours = diff_seconds / 3600.0
            return round(diff_hours, 2)
        except Exception as e:
            print(f"Erreur lors de la récupération de l'âge du wallet : {e}")
            return 0.0

    def validate_and_scrape(self, url: str, selectors: list, tag: str, class_name: str):
        """
        Fonction principale pour valider, scraper et envoyer le message.
        On réduit les temps, tout en gardant un minimum d'attentes pour la fiabilité.
        """
        try:
            print(f"Chargement de la page : {url}")
            self.driver.get(url)
            time.sleep(random.uniform(1, 2))

            # Fermer la fenêtre modale 'I agree...' si elle existe
            try:
                agree_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(), 'I agree to the Terms and Conditions')]")
                    )
                )
                agree_button.click()
                print("Fenêtre modale fermée avec succès.")
                time.sleep(random.uniform(1, 2))
            except Exception:
                print("Aucune fenêtre modale détectée.")

            # Effectuer les clics initiaux (sélecteurs)
            for selector in selectors:
                self.click_element(selector['by'], selector['identifier'])

            refresh_counter = 0

            while True:
                # On attend un petit peu avant de lire le code source
                time.sleep(random.uniform(1, 2))

                soup_after_click = BeautifulSoup(self.driver.page_source, 'html.parser')
                agent_elements = self.extract_data(soup_after_click, tag, class_name)

                if agent_elements:
                    first_agent = agent_elements[0]
                    formatted_agent = self.format_data(str(first_agent))
                    token = formatted_agent.get('Token', "")
                    name = formatted_agent.get('Nom', "")
                    mcap = formatted_agent.get('Mcap', "")
                    link = formatted_agent.get('Lien', "")

                    if token and token != self.last_token and name and mcap:
                        # Petit délai avant de continuer
                        time.sleep(random.uniform(0.5, 1))
                        self.last_token = token

                        # Aller chercher l'adresse token
                        adresse_token, social_links = self.navigate_and_copy_address(link)

                        # Récupérer l'adresse du créateur + âge
                        creator_addr = "Non disponible"
                        hours_since_creation = 0.0
                        if adresse_token:
                            try:
                                creator_addr = self.get_contract_creator_basescan(
                                    adresse_token, "6HSW2H9XS5SK2RM852AC7776KZCNRTGB39"
                                )
                                hours_since_creation = self.get_wallet_age_in_hours(
                                    creator_addr, "6HSW2H9XS5SK2RM852AC7776KZCNRTGB39"
                                )
                            except Exception as e:
                                print(f"Impossible de récupérer l'adresse du créateur : {e}")

                        twitter_url = social_links.get('twitter', "")
                        site_url = social_links.get('siteweb', "")
                        telegram_url = social_links.get('telegram', "")

                        # Lien de l'agent (simple texte, pas cliquable)
                        agent_url = f"https://creator.bid{link}"

                        # CA cliquable
                        if adresse_token:
                            ca_url = f"https://basescan.org/token/{adresse_token}"
                            ca_html = f"{adresse_token} (<a href='{ca_url}'>View</a>)"
                        else:
                            ca_html = "Non disponible"

                        # Creator address cliquable
                        if creator_addr != "Non disponible":
                            creator_url = f"https://basescan.org/address/{creator_addr}"
                            creator_html = f"{creator_addr} (<a href='{creator_url}'>View</a>)"
                        else:
                            creator_html = "Non disponible"

                        # Construct the message in HTML
                        message = (
                            f"<b>NEW AGENT DEPLOYED</b>\n"
                            f"Mcap: {mcap}\n"
                            f"Token: {token}\n"
                            f"Name: {name}\n"
                            # Lien agent en clair, non cliquable
                            f"Link: {agent_url}\n"
                            # CA cliquable
                            f"CA: {ca_html}\n"
                            # Creator address cliquable
                            f"Creator address: {creator_html} "
                            f"(created since: {hours_since_creation} hours)\n"
                            f"Twitter: {twitter_url}\n"
                            f"Site: {site_url}\n"
                            f"Telegram: {telegram_url}"
                        )
                        print(message)
                        self.send_telegram_message(message)

                        # Revenir à la page précédente
                        self.driver.back()
                        time.sleep(random.uniform(1, 2))
                        refresh_counter = 0
                    else:
                        print(f"Token {token} inchangé, message non envoyé.")
                else:
                    print("Aucun agent trouvé.")

                # Gestion du refresh_counter
                refresh_counter += 1
                if refresh_counter > 30:
                    print("Page potentiellement bloquée, on rafraîchit la page.")
                    self.driver.refresh()
                    time.sleep(random.uniform(1, 2))
                    for selector in selectors:
                        self.click_element(selector['by'], selector['identifier'])
                    refresh_counter = 0

                # Petite pause en fin de boucle
                time.sleep(random.uniform(1, 2))

        except Exception as e:
            print(f"Erreur lors du scraping ou du clic : {e}")
        finally:
            self.close()

    def navigate_and_copy_address(self, partial_link: str):
        """
        Navigue vers la page d'un agent, clique pour copier l'adresse du token,
        et renvoie (copied_address, social_links).
        """
        try:
            full_url = f"https://creator.bid{partial_link}"
            print(f"Navigation vers : {full_url}")
            self.driver.get(full_url)
            time.sleep(random.uniform(1, 2))

            soup_agent_page = BeautifulSoup(self.driver.page_source, 'html.parser')
            social_links = self.extract_socials(soup_agent_page, 'AgentHeader_socials__Ao_7d') or {}

            copy_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "h5.AgentKeyChart_copy__JrS0u"))
            )
            copy_button.click()
            print("H5 cliqué avec succès.")

            copied_address = self.driver.execute_script("return navigator.clipboard.readText();")
            print(f"Adresse copiée : {copied_address}")
            time.sleep(random.uniform(0.5, 1))

            return copied_address or "", social_links

        except Exception as e:
            print(f"Erreur lors de la navigation ou de la récupération de l'adresse : {e}")
            return "", {}

    def extract_data(self, soup: BeautifulSoup, tag: str, class_name: str) -> list:
        """
        Extrait les div.AgentListItem_agent__maDHv de la 2e div.AgentList_agents__3ZX5J
        """
        parent_divs = soup.find_all('div', class_=class_name)
        if len(parent_divs) > 1:
            second_div = parent_divs[1]
            agent_elements = second_div.find_all('div', class_='AgentListItem_agent__maDHv')
            return [str(element) for element in agent_elements]
        else:
            print("Il n'y a pas de deuxième div AgentList_agents__3ZX5J.")
            return []

    def extract_socials(self, soup: BeautifulSoup, class_name: str) -> dict:
        """
        Extrait les liens sociaux (twitter, site web, telegram) depuis la div.
        """
        parent_div = soup.find('div', class_=class_name)
        if not parent_div:
            return {}
        links = parent_div.find_all('a', href=True)
        socials = {
            'twitter': links[0]['href'] if len(links) > 0 else "",
            'siteweb': links[1]['href'] if len(links) > 1 else "",
            'telegram': links[2]['href'] if len(links) > 2 else ""
        }
        return socials

    def format_data(self, raw_data: str) -> dict:
        """
        Formate les données extraites pour obtenir token, mcap, name et le lien (href).
        """
        try:
            soup = BeautifulSoup(raw_data, 'html.parser')
            mcap = soup.find('div', class_='AgentListItem_marketcap__8GMUk').text.strip()
            token = soup.find('div', class_='AgentListItem_agentKeyTag__8cWPf').text.strip().replace('$', '')
            name = soup.find('div', class_='AgentListItem_name__Plxwu').text.strip()
            link_element = soup.find('a', href=True)
            link = link_element['href'] if link_element else ""
            return {
                "Mcap": mcap,
                "Token": token,
                "Nom": name,
                "Lien": link
            }
        except Exception as e:
            print(f"Erreur lors du formatage des données : {e}")
            return {
                "Mcap": "",
                "Token": "",
                "Nom": "",
                "Lien": ""
            }

# main.py
def main():
    telegram_token = '7666836262:AAGl1zYPDFpliy-lki0V51L1ZeYTGw4Dshs'
    channel_id = '-1002497694021'

    scraper = WebScraper(telegram_token, channel_id)
    try:
        url = 'https://creator.bid/agents'
        selectors = [
            {
                'by': By.XPATH,
                'identifier': "//div[contains(@class, 'Select_selectedOption')]"
            },
            {
                'by': By.XPATH,
                'identifier': "//div[contains(@class, 'Select_left')]//span[contains(text(), 'Created at')]"
            }
        ]
        tag = 'div'
        class_name = 'AgentList_agents__3ZX5J'
        scraper.validate_and_scrape(url, selectors, tag, class_name)
    finally:
        scraper.close()

if __name__ == "__main__":
    main()

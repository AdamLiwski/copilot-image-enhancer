import os
import time
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# --- KONFIGURACJA ŚCIEŻEK (RELATYWNE) ---
# Pobiera ścieżkę do folderu, w którym znajduje się ten skrypt
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGES_FOLDER = os.path.join(BASE_DIR, "input_images")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output_images")
SESSION_FOLDER = os.path.join(BASE_DIR, "edge_profile")

COPILOT_URL = "https://copilot.microsoft.com/"
WAIT_TIME = 30
GENERATION_WAIT = 180

# Upewnij się, że foldery istnieją
os.makedirs(IMAGES_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(SESSION_FOLDER, exist_ok=True)

def initialize_driver():
    """Inicjalizacja przeglądarki Edge z lokalnym profilem użytkownika w folderze projektu."""
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    
    # Ustawienie lokalnego folderu dla danych przeglądarki (sesja, ciasteczka)
    options.add_argument(f"user-data-dir={SESSION_FOLDER}")
    options.add_argument("profile-directory=Default")

    # Preferencje pobierania
    prefs = {
        "download.default_directory": OUTPUT_FOLDER,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    # Automatyczne zarządzanie sterownikiem Edge (nie trzeba podawać ścieżki exe)
    service = EdgeService(EdgeChromiumDriverManager().install())
    driver = webdriver.Edge(service=service, options=options)
    return driver

def upload_image_by_attachment(driver, image_path):
    """Dodaje zdjęcie przez menu plusik i spinacz."""
    try:
        plus_button = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="plus-button"]'))
        )
        plus_button.click()
        time.sleep(1)

        attach_button = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="file-upload-button"]'))
        )
        attach_button.click()
        time.sleep(1)

        # Podajemy bezwzględną ścieżkę dla pyautogui (system plików tego wymaga)
        abs_image_path = os.path.abspath(image_path)
        pyautogui.write(abs_image_path)
        pyautogui.press('enter')
        
        # Czekamy aż miniatura się załaduje (zwiększono czas dla pewności)
        time.sleep(5)
        print(f"Załączono zdjęcie: {os.path.basename(image_path)}")
        return True
    except Exception as e:
        print(f"Błąd podczas załączania zdjęcia: {e}")
        return False

def send_prompt(driver, prompt):
    """Wysyłanie promptu."""
    try:
        text_area = WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#userInput"))
        )
        text_area.click()
        time.sleep(0.5)
        text_area.send_keys(prompt)
        text_area.send_keys(Keys.RETURN)
        print(f"Wysłano prompt.")
        return True
    except Exception as e:
        print(f"Błąd podczas wysyłania promptu: {e}")
        return False

def save_generated_image_from_button(driver, button, file_path):
    """Kliknij przycisk, pobierz i zmień nazwę."""
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", button)
        print(f"Pobieranie...")

        timeout = 30
        start_time = time.time()
        before_files = set(os.listdir(OUTPUT_FOLDER))
        downloaded_file = None

        while time.time() - start_time < timeout:
            after_files = set(os.listdir(OUTPUT_FOLDER))
            new_files = after_files - before_files
            # Ignorujemy pliki tymczasowe (np. .crdownload)
            valid_new_files = [f for f in new_files if not f.endswith('.crdownload') and not f.endswith('.tmp')]
            
            if valid_new_files:
                downloaded_file = valid_new_files[0]
                break
            time.sleep(1)

        if not downloaded_file:
            print(f"Nie wykryto nowego pliku w: {OUTPUT_FOLDER}")
            return False

        # Czekamy chwilę, aby upewnić się, że system zwolnił uchwyt pliku
        time.sleep(1)
        
        old_path = os.path.join(OUTPUT_FOLDER, downloaded_file)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        os.rename(old_path, file_path)
        print(f"Zapisano jako: {os.path.basename(file_path)}")
        return True
    except Exception as e:
        print(f"Błąd zapisu: {e}")
        return False

def process_single_image(driver, image_path):
    """Przetwarzanie jednego zdjęcia."""
    try:
        # Otwórz nową kartę
        driver.execute_script(f"window.open('{COPILOT_URL}');")
        driver.switch_to.window(driver.window_handles[-1])
        
        # Dłuższy czas na załadowanie strony dla pewności
        time.sleep(5)

        if not upload_image_by_attachment(driver, image_path):
            return False

        # --- PROMPT ---
        new_prompt = (
            "Przerysuj to zdjęcie produktowe, zachowując dokładnie tę samą kompozycję, kształt produktu, "
            "ułożenie i oryginalne odcienie kolorów. Skup się na subtelnej modyfikacji detali, "
            "oświetlenia i cieni, aby nadać mu świeży, lekko odmienny wygląd, unikając jednocześnie "
            "identyczności z oryginałem (dla algorytmów anty-duplikatowych). "
            "Wprowadź minimalne, ale widoczne różnice w teksturze, odbiciach światła i głębi. "
            "Tło musi pozostać idealnie białe (RGB 255,255,255), bez marginesów i ramek. "
            "Format: kwadrat 1:1."
        )

        if not send_prompt(driver, new_prompt):
            return False

        # Czekanie na wynik
        print("Oczekiwanie na wygenerowanie obrazu...")
        WebDriverWait(driver, GENERATION_WAIT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-testid='ai-image-download-button']"))
        )
        
        # Pobieranie
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='ai-image-download-button']")
        if not buttons:
            print("Błąd: Brak przycisku pobierania.")
            return False

        # Nazwa pliku wyjściowego
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        output_path = os.path.join(OUTPUT_FOLDER, f"{base_name}_new.png")
        
        # Używamy ostatniego przycisku (zazwyczaj ostatni to ten właściwy w czacie)
        return save_generated_image_from_button(driver, buttons[-1], output_path)

    except Exception as e:
        print(f"Błąd w procesie: {e}")
        return False
    finally:
        # Sprzątanie kart (zostawiamy pierwszą, zamykamy roboczą)
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])

def main():
    # Sprawdzenie czy są zdjęcia
    if not os.path.exists(IMAGES_FOLDER):
        print(f"Stwórz folder '{IMAGES_FOLDER}' i wrzuć tam zdjęcia.")
        return

    image_files = [f for f in os.listdir(IMAGES_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if not image_files:
        print(f"Folder '{IMAGES_FOLDER}' jest pusty.")
        return

    print(f"Znaleziono {len(image_files)} zdjęć.")
    print("UWAGA: Przy pierwszym uruchomieniu będziesz musiał się zalogować do konta Microsoft w otwartym oknie.")
    print("Masz na to 60 sekund po uruchomieniu przeglądarki, potem skrypt ruszy dalej.")

    driver = initialize_driver()
    
    # Pierwsze otwarcie - czas na ewentualne logowanie, jeśli ciasteczka wygasły lub to pierwsze uruchomienie
    driver.get(COPILOT_URL)
    time.sleep(5) 

    try:
        for i, img_file in enumerate(image_files, 1):
            img_path = os.path.join(IMAGES_FOLDER, img_file)
            print(f"\n[{i}/{len(image_files)}] Przetwarzanie: {img_file}")
            
            success = process_single_image(driver, img_path)
            
            if success:
                print("Sukces.")
            else:
                print("Porażka.")

            # Losowa pauza, żeby wyglądać bardziej jak człowiek
            time.sleep(random.uniform(5, 10))

    except KeyboardInterrupt:
        print("\nPrzerwano (Ctrl+C).")
    finally:
        driver.quit()
        print("Koniec pracy.")

if __name__ == "__main__":
    import random # Dodany brakujący import
    main()
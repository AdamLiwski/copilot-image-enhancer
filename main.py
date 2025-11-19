import os
import time
import io
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import random

# Biblioteki do obsługi schowka
import win32clipboard
from PIL import Image

# --- KONFIGURACJA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_FOLDER = os.path.join(BASE_DIR, "input_images")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output_images")
SESSION_FOLDER = os.path.join(BASE_DIR, "edge_profile")
LOCAL_DRIVER_NAME = "msedgedriver.exe" 
PROGRESS_LOG_FILE = os.path.join(BASE_DIR, "progress_log.txt") # Plik do śledzenia postępu

COPILOT_URL = "https://copilot.microsoft.com/"
WAIT_TIME = 30
GENERATION_WAIT = 180
MAX_RETRIES = 2  

# --- ZMIENNOŚĆ DLA ALLEGRO ---
# Losowe style oświetlenia, aby zmylić algorytmy wykrywające duplikaty
LIGHTING_STYLES = [
    "oświetlenie boczne z głębokimi cieniami (dramatic side lighting)",
    "miękkie oświetlenie typu softbox (soft studio lighting)",
    "ostre światło konturowe (rim lighting)",
    "oświetlenie z góry typu 'butterfly' (high angle lighting)",
    "ciepłe, słoneczne oświetlenie (warm sunlight)",
    "chłodne, nowoczesne oświetlenie studyjne (cool studio light)"
]

os.makedirs(IMAGES_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(SESSION_FOLDER, exist_ok=True)

def save_progress_log(filename):
    """Zapisuje nazwę pliku do logu postępu."""
    with open(PROGRESS_LOG_FILE, "a") as f:
        f.write(filename + "\n")

def get_completed_files():
    """Wczytuje listę ukończonych plików."""
    if not os.path.exists(PROGRESS_LOG_FILE):
        return set()
    with open(PROGRESS_LOG_FILE, "r") as f:
        return set(line.strip() for line in f)

def initialize_driver():
    """Inicjalizacja przeglądarki Edge."""
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument(f"user-data-dir={SESSION_FOLDER}")
    options.add_argument("profile-directory=Default")

    prefs = {
        "download.default_directory": OUTPUT_FOLDER,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    service = None
    try:
        print("Próba automatycznej konfiguracji sterownika Edge...")
        driver_path = EdgeChromiumDriverManager().install()
        service = EdgeService(driver_path)
    except Exception as e:
        print(f"\n[INFO] Tryb online nieudany, szukam sterownika lokalnie...")
        local_driver_path = os.path.join(BASE_DIR, LOCAL_DRIVER_NAME)
        if os.path.exists(local_driver_path):
            service = EdgeService(local_driver_path)
        else:
            raise Exception("Brak pliku msedgedriver.exe")

    driver = webdriver.Edge(service=service, options=options)
    return driver

def copy_image_to_clipboard(image_path):
    """Kopiuje obraz do schowka."""
    try:
        image = Image.open(image_path)
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        print(f"Błąd schowka: {e}")
        return False

def get_text_area(driver):
    """Pomocnicza funkcja do znajdowania pola tekstowego."""
    return WebDriverWait(driver, WAIT_TIME).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[data-testid="composer-input"]'))
    )

def paste_image_and_send_prompt(driver, prompt):
    """Wkleja obraz i wysyła prompt (jeden krok)."""
    try:
        text_area = get_text_area(driver)
        
        # --- Symulacja użytkownika ---
        text_area.click() 
        time.sleep(random.uniform(0.5, 1.5))
        
        # 1. Wklejenie obrazu
        print("Wklejanie obrazu...")
        text_area.send_keys(Keys.CONTROL, 'v')
        time.sleep(random.uniform(7, 10)) # Czas na upload

        # 2. Wpisanie promptu
        text_area.send_keys(prompt)
        time.sleep(random.uniform(1.5, 3))
        text_area.send_keys(Keys.RETURN)
        print("Wysłano zapytanie.")
        return True
    except Exception as e:
        print(f"Błąd wysyłania: {e}")
        return False

def wait_for_result_or_error(driver):
    """Czeka na wynik LUB na komunikaty błędów."""
    start_time = time.time()
    print("Oczekiwanie na wynik...")
    
    while time.time() - start_time < GENERATION_WAIT:
        try:
            # 1. Sukces
            buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='ai-image-download-button']")
            if buttons:
                return "success", buttons[-1]

            page_source = driver.page_source

            # 2. Błąd generowania (Content Filter)
            if "Niestety, nie udało mi się" in page_source or "nie mogę wygenerować" in page_source:
                return "error_content", None
            
            # 3. Błąd serwera / przeciążenia (Rate Limit)
            if "having trouble responding" in page_source or "Coś poszło nie tak" in page_source or "Niepowodzenie" in page_source:
                return "error_server", None

        except Exception:
            pass
        
        time.sleep(1)
    
    return "timeout", None

def save_image(driver, button, file_path, original_filename):
    """Pobiera plik i loguje sukces."""
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", button)
        print(f"Pobieranie pliku...")

        timeout = 30
        start_time = time.time()
        before_files = set(os.listdir(OUTPUT_FOLDER))
        downloaded_file = None

        while time.time() - start_time < timeout:
            after_files = set(os.listdir(OUTPUT_FOLDER))
            new_files = after_files - before_files
            valid_new_files = [f for f in new_files if not f.endswith('.crdownload') and not f.endswith('.tmp')]
            if valid_new_files:
                downloaded_file = valid_new_files[0]
                break
            time.sleep(1)

        if not downloaded_file:
            return False

        time.sleep(1)
        old_path = os.path.join(OUTPUT_FOLDER, downloaded_file)
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(old_path, file_path)
        
        # Zapis logu tylko po sukcesie
        save_progress_log(original_filename)

        return True
    except Exception as e:
        print(f"Błąd zapisu: {e}")
        return False

def process_single_image(driver, image_path, retry_count=0):
    
    if retry_count >= MAX_RETRIES:
        print("!!! Limit prób wyczerpany. Pomijam zdjęcie.")
        return False

    original_filename = os.path.basename(image_path)

    try:
        print(f"--- Próba {retry_count + 1}/{MAX_RETRIES} ---")
        print("Odświeżanie Copilota...")
        driver.get(COPILOT_URL)
        # Losowy czas na załadowanie
        time.sleep(random.uniform(7, 12)) 

        # Dodatkowe kliknięcie w pole, aby upewnić się, że jest aktywne
        try:
            get_text_area(driver).click()
            time.sleep(1)
        except:
            print("Nie udało się kliknąć pola tekstowego.")

        if not copy_image_to_clipboard(image_path):
            return False
        
        # --- ZŁOŻONY PROMPT JEDNOETAPOWY Z LOSOWOŚCIĄ ---
        
        # Losowanie stylu
        style = random.choice(LIGHTING_STYLES)
        print(f"Wylosowany styl: {style}")

        main_prompt = (
            "Na podstawie załączonego obrazu, stwórz **nowe, unikalne** zdjęcie produktowe tego obiektu. "
            "Zachowaj główną kompozycję, kształt i kolorystykę produktu, ale zmodernizuj i przerysuj detale, "
            f"używając realistycznego stylu z **{style}**. "
            "Wprowadź drobne różnice w cieniach, odbiciach i kącie widzenia, aby zdjęcie było unikalne "
            "(dla ominięcia detekcji duplikatów). "
            "Tło musi być idealnie czysto białe (RGB 255, 255, 255). Format kwadratowy, jakość 4K."
        )
        
        if not paste_image_and_send_prompt(driver, main_prompt):
            return False

        status, result = wait_for_result_or_error(driver)

        if status == "success":
            base_name = os.path.splitext(original_filename)[0]
            output_path = os.path.join(OUTPUT_FOLDER, f"{base_name}_new.png")
            if save_image(driver, result, output_path, original_filename):
                print(f"Sukces: {os.path.basename(output_path)}")
                return True
            else:
                print("Błąd zapisu pliku.")
                return False
        
        elif status == "error_content":
            print("BŁĄD TREŚCI (AI odmówiło).")
            if retry_count == 0:
                time.sleep(5)
                return process_single_image(driver, image_path, retry_count + 1)
            return False
        
        elif status == "error_server":
            # --- ZMIANA: DŁUGA PAUZA PRZY BANIE SERWERA ---
            pause_time = random.uniform(300, 600) # 5 do 10 minut
            print(f"BŁĄD SERWERA/BANA (Wykryto bota/Przeciążenie). Przerwa na {pause_time:.0f}s ({pause_time/60:.1f} min)...") 
            time.sleep(pause_time)
            return process_single_image(driver, image_path, retry_count + 1)
        
        else:
            print("Timeout. Spróbuję ponownie.")
            time.sleep(random.uniform(5, 10))
            return process_single_image(driver, image_path, retry_count + 1)

    except Exception as e:
        print(f"Nieoczekiwany błąd sesji: {e}")
        return False

def main():
    if not os.path.exists(IMAGES_FOLDER):
        print(f"Brak folderu {IMAGES_FOLDER}")
        return

    image_files = [f for f in os.listdir(IMAGES_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if not image_files:
        print("Brak zdjęć do przetworzenia.")
        return
    
    completed_files = get_completed_files()
    files_to_process = [f for f in image_files if f not in completed_files]
    
    print(f"Znaleziono {len(image_files)} zdjęć. Ukończono: {len(completed_files)}. Do przetworzenia: {len(files_to_process)}")
    
    if not files_to_process:
        print("Wszystkie pliki zostały już przetworzone.")
        return

    try:
        driver = initialize_driver()
    except Exception as e:
        print(f"Start nieudany: {e}")
        return
    
    print("Startuje przeglądarkę... Masz 60s na ewentualne logowanie.")
    driver.get(COPILOT_URL)
    time.sleep(5)

    try:
        total_processed = len(image_files)
        current_index = len(image_files) - len(files_to_process)
        
        for i, img_file in enumerate(files_to_process, 1):
            img_path = os.path.join(IMAGES_FOLDER, img_file)
            print(f"\n[{i + current_index}/{total_processed}] Plik: {img_file}")
            
            process_single_image(driver, img_path)
            
            sleep_time = random.uniform(20, 30)
            print(f"Przerwa regeneracyjna {sleep_time:.1f}s...")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nStop.")
    finally:
        if driver:
            # Zamykamy drivera, aby nie zostawiać wiszącej sesji
            driver.quit()

if __name__ == "__main__":
    main()
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ============ ⚙️ Selenium Setup ============
options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-popup-blocking")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
driver = webdriver.Chrome(options=options)

# ============ 📄 Načítanie linkov ============
with open("links.txt", "r") as f:
    linky = [line.strip() for line in f if line.strip()]

# ============ 🔁 Spracovanie každého linku ============
for link in linky:
    print(f"\nSpracúvam: {link}")
    driver.get(link)
    time.sleep(3)

    # Helper funkcia: zavrie popup ak sa otvoril
    def zavri_popup():
        main_window = driver.current_window_handle
        time.sleep(2)
        all_windows = driver.window_handles
        for handle in all_windows:
            if handle != main_window:
                print("🧹 Zatváram popup...")
                driver.switch_to.window(handle)
                driver.close()
        driver.switch_to.window(main_window)

    # 🔘 Krok 1: Continue to download
    try:
        time.sleep(3)
        button = driver.find_element(By.ID, 'method_free')
        driver.execute_script("arguments[0].scrollIntoView(true);", button)
        time.sleep(2)

        # odstráni overlay prvky (reklamy)
        driver.execute_script("""
            let overlays = Array.from(document.querySelectorAll('div'))
                .filter(el => getComputedStyle(el).zIndex > 10000);
            overlays.forEach(el => el.remove());
        """)

        # klik + zavri popup
        driver.execute_script("arguments[0].click();", button)
        zavri_popup()
        print("✔️ Klikol som na: Continue to download")

    except Exception as e:
        print("❌ Chyba pri 'Continue to download':", e)
        continue

       # 🔘 Krok 2: Download (hneď po Continue to download)
    try:
        print("⏳ Hľadám tlačidlo 'Download'...")
        for _ in range(20):
            try:
                download_button = driver.find_element(By.XPATH, '//button[contains(@class, "bg-blue-600") and contains(., "Download")]')
                if download_button.is_displayed():
                    break
            except:
                pass
            time.sleep(0.5)

        # Zabezpečiť scroll a klik
        driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", download_button)
        zavri_popup()
        print("✔️ Klikol som na: Download")

    except Exception as e:
        print("❌ Chyba pri 'Download':", e)
        continue

    # 🔘 Krok 3: Continue (záverečný krok po čakaní 5s)
    try:
        print("⏳ Čakám a klikám na tlačidlo 'Continue'...")
        # Počkám 5 sekúnd (aby sa tlačidlo načítalo)
        time.sleep(5)

        continue_button = driver.find_element(By.XPATH, '//button[contains(., "Continue")]')
        driver.execute_script("arguments[0].scrollIntoView(true);", continue_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", continue_button)
        zavri_popup()
        print("✔️ Klikol som na: Continue")

    except Exception as e:
        print("❌ Chyba pri 'Continue':", e)

    # 🕒 Čakaj 2 minúty na stiahnutie (500MB)
    print("🛑 Čakám 1 minúty na stiahnutie...")
    time.sleep(60)

# ============ ✅ Hotovo ============
print("\n🎉 Všetky linky spracované. Koniec.")
driver.quit()

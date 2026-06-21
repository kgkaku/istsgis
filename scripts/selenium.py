# scripts/fingerprint_selenium.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import json
import os
from datetime import datetime

def get_fresh_fingerprint_selenium():
    """
    Selenium Headless Chrome দিয়ে cna ফিঙ্গারপ্রিন্ট নেওয়া
    """
    options = Options()
    
    # Headless মোড (GitHub Actions-এর জন্য)
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    # User-Agent সেট
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # ব্রাউজার লঞ্চ
    driver = webdriver.Chrome(options=options)
    
    # WebDriver ডিটেকশন বাইপাস
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        '''
    })
    
    try:
        # CCTV পেজ লোড
        print("🔄 Loading CCTV website...")
        driver.get('https://tv.cctv.com/live/cctv1/')
        driver.implicitly_wait(5)
        
        # কুকি সংগ্রহ
        cookies = driver.get_cookies()
        fingerprint = None
        for cookie in cookies:
            if cookie['name'] == 'cna':
                fingerprint = cookie['value']
                break
        
        if fingerprint:
            print(f"✅ New fingerprint: {fingerprint[:20]}...")
            return fingerprint, cookies
        else:
            print("⚠️ cna cookie not found")
            return None, None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None
    finally:
        driver.quit()

def save_fingerprint(fingerprint, cookies=None):
    config = {}
    if os.path.exists('config.json'):
        with open('config.json', 'r') as f:
            config = json.load(f)
    
    config['fingerprint'] = fingerprint
    config['fingerprint_updated'] = datetime.now().isoformat()
    if cookies:
        config['cookies'] = cookies
    
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✅ Fingerprint saved to config.json")

if __name__ == "__main__":
    fp, cookies = get_fresh_fingerprint_selenium()
    if fp:
        save_fingerprint(fp, cookies)

#!/usr/bin/env python3
"""
CCTV Live Stream Extractor - All-in-One Script
- Auto-installs dependencies (pip install)
- Auto-refreshes fingerprint (Playwright)
- Generates cctv.m3u + cctv.json
- Runs every 2 hours via GitHub Action
"""

import subprocess
import sys
import os
import json
import time
import hashlib
import hmac
import base64
import random
import requests
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from playwright.sync_api import sync_playwright

# ============================================================
# AUTO-INSTALL DEPENDENCIES
# ============================================================

def install_dependencies():
    """Auto-install required packages"""
    required = ['requests', 'pycryptodome', 'playwright']
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            print(f"📦 Installing {pkg}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])
    
    # Playwright browsers
    try:
        subprocess.check_call([sys.executable, '-m', 'playwright', 'install', 'chromium', '--quiet'])
    except:
        pass

# Run auto-install
install_dependencies()

# ============================================================
# CONFIGURATION
# ============================================================

CONFIG_FILE = "config.json"
OUTPUT_DIR = "output"

# Secret keys (from CCTV code)
SECRET_1 = "B4B51E8523157ED8D17ADB76041BCD09"
SECRET_2 = "47899B86370B879139C08EA3B5E88267"

# DRM decryption keys (from CCTV code)
DECRYPT_KEY = base64.b64decode("0hdiziKsev1LRe24oGTMPwfg9f+kcCWQ56sxi+jMAKE=")
DECRYPT_IV = base64.b64decode("JMo0DT+7XkLZcT1KE1Nv8rOXwxDc7UmOB7eVzx11MvU=")

# All channels
CHANNELS = [
    'cctv1', 'cctv2', 'cctv3', 'cctv4', 'cctv5',
    'cctv5plus', 'cctv6', 'cctv7', 'cctv8',
    'cctv10', 'cctv11', 'cctv12', 'cctv13',
    'cctv15', 'cctv16', 'cctv17',
    'cctvnews', 'cctveurope', 'cctvamerica',
    'cctvjilu', 'cctvchild'
]

CHANNEL_NAMES = {
    'cctv1': 'CCTV-1 综合', 'cctv2': 'CCTV-2 财经',
    'cctv3': 'CCTV-3 综艺', 'cctv4': 'CCTV-4 中文国际',
    'cctv5': 'CCTV-5 体育', 'cctv5plus': 'CCTV-5+ 体育赛事',
    'cctv6': 'CCTV-6 电影', 'cctv7': 'CCTV-7 国防军事',
    'cctv8': 'CCTV-8 电视剧', 'cctv10': 'CCTV-10 科教',
    'cctv11': 'CCTV-11 戏曲', 'cctv12': 'CCTV-12 社会与法',
    'cctv13': 'CCTV-13 新闻', 'cctv15': 'CCTV-15 音乐',
    'cctv16': 'CCTV-16 奥林匹克', 'cctv17': 'CCTV-17 农业农村',
    'cctvnews': 'CGTN', 'cctveurope': 'CGTN Europe',
    'cctvamerica': 'CGTN America', 'cctvjilu': 'CCTV-纪录',
    'cctvchild': 'CCTV-少儿'
}

# ============================================================
# FINGERPRINT FUNCTIONS
# ============================================================

def get_fresh_fingerprint():
    """Get fresh cna fingerprint using Playwright headless browser"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                viewport={"width": 385, "height": 854},
                locale="zh-CN",
                timezone_id="Asia/Shanghai"
            )
            page = context.new_page()
            page.goto("https://tv.cctv.com/live/cctv1/", wait_until="networkidle")
            
            fingerprint = page.evaluate("""
                () => {
                    const cookie = document.cookie.split('; ').find(row => row.startsWith('cna='));
                    return cookie ? cookie.split('=')[1] : null;
                }
            """)
            browser.close()
            return fingerprint
    except Exception as e:
        print(f"❌ Fingerprint refresh error: {e}")
        return None

def load_fingerprint():
    """Load fingerprint from config, refresh if missing"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        fp = config.get('fingerprint')
        if fp:
            print(f"✅ Using cached fingerprint: {fp[:20]}...")
            return fp
    
    print("🔄 Getting fresh fingerprint...")
    fp = get_fresh_fingerprint()
    if fp:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                'fingerprint': fp,
                'updated': datetime.now().isoformat()
            }, f, indent=2)
        print(f"✅ Saved new fingerprint: {fp[:20]}...")
        return fp
    
    print("❌ Failed to get fingerprint!")
    return None

# ============================================================
# CORE FUNCTIONS
# ============================================================

def generate_auth_key(channel, fingerprint):
    """Generate CCTV auth-key using HMAC-SHA256"""
    timestamp = str(int(time.time() * 1000))[:10]
    raw = timestamp + SECRET_1 + SECRET_1 + fingerprint
    signature = hmac.new(
        SECRET_2.encode('utf-8'),
        raw.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()
    random_num = random.randint(100, 999)
    return f"{timestamp}-{random_num}-{signature}", timestamp

def decrypt_license(response_text):
    """Decrypt CCTV license response"""
    try:
        if response_text.strip().startswith('{'):
            return json.loads(response_text)
        encrypted_bytes = base64.b64decode(response_text)
        cipher = AES.new(DECRYPT_KEY, AES.MODE_CBC, DECRYPT_IV)
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        decrypted = unpad(decrypted_bytes, AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        return {"public": "0", "tip_msg": str(e)}

def get_license(channel, fingerprint):
    """Get license from vdnx API"""
    auth_key, timestamp = generate_auth_key(channel, fingerprint)
    url = "https://vdnx.live.cntv.cn/api/v3/vdn/live"
    params = {
        "channel": channel,
        "vn": "1000",
        "pdrm": "1",
        "uid": fingerprint,
        "hbss": timestamp
    }
    headers = {
        "auth-key": auth_key,
        "Referer": "https://tv.cctv.com/",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            return decrypt_license(response.text)
        return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def get_epg(channel):
    """Get EPG data from cbox"""
    date = datetime.now().strftime("%Y/%m/%d")
    url = f"https://cbox.cntv.cn/epg/ctlist/{date}/{channel}.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def extract_stream_url(license_data, channel):
    """Extract M3U8 URL from license"""
    if not license_data:
        return None
    manifest = license_data.get('manifest', {})
    stream_url = manifest.get('hls_cdrm') or manifest.get('hls_nd', '')
    return stream_url.replace('${channel}', channel) if stream_url else None

# ============================================================
# MAIN
# ============================================================

def main():
    print("="*60)
    print("🚀 CCTV LIVE STREAM EXTRACTOR")
    print("="*60)
    
    # 1. Fingerprint
    fingerprint = load_fingerprint()
    if not fingerprint:
        print("❌ No fingerprint available!")
        sys.exit(1)
    
    # 2. Output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 3. Process all channels
    channels_data = {}
    success_count = 0
    
    print(f"\n📡 Processing {len(CHANNELS)} channels...")
    
    for i, channel in enumerate(CHANNELS, 1):
        print(f"\n[{i}/{len(CHANNELS)}] {channel} - {CHANNEL_NAMES.get(channel, channel)}")
        
        try:
            license_data = get_license(channel, fingerprint)
            if license_data and license_data.get('public') == '1':
                stream_url = extract_stream_url(license_data, channel)
                if stream_url:
                    channels_data[channel] = {
                        'name': CHANNEL_NAMES.get(channel, channel),
                        'url': stream_url,
                        'logo': f"https://piccpndks.v.kcdnvip.com/pic/{channel}_2.png",
                        'drm': bool(license_data.get('manifest', {}).get('hls_cdrm')),
                        'epg': get_epg(channel)
                    }
                    success_count += 1
                    print(f"   ✅ Stream URL found")
                else:
                    print(f"   ⚠️ No stream URL")
            else:
                print(f"   ⚠️ No license (public={license_data.get('public') if license_data else 'None'})")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n✅ Success: {success_count}/{len(CHANNELS)} channels")
    
    # 4. Generate M3U
    m3u_content = "#EXTM3U\n"
    m3u_content += f"# Updated: {datetime.now().isoformat()}\n\n"
    
    for channel, data in channels_data.items():
        if data.get('url'):
            m3u_content += f'#EXTINF:-1 tvg-id="{channel}" tvg-logo="{data["logo"]}" group-title="CCTV",{data["name"]}\n'
            m3u_content += f'#EXTVLCOPT:http-referrer=https://tv.cctv.com/\n'
            m3u_content += f'{data["url"]}\n\n'
    
    m3u_path = os.path.join(OUTPUT_DIR, 'cctv.m3u')
    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write(m3u_content)
    print(f"✅ M3U saved: {m3u_path}")
    
    # 5. Generate JSON
    json_data = {
        'version': datetime.now().isoformat(),
        'fingerprint': fingerprint,
        'channels': channels_data
    }
    
    json_path = os.path.join(OUTPUT_DIR, 'cctv.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {json_path}")
    
    print("\n🎉 Done!")

if __name__ == "__main__":
    main()

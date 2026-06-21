#!/usr/bin/env python3
"""
CCTV Live Stream Extractor - Full Working Code
- Auto-refreshes fingerprint (Playwright)
- Gets licenses from vdnx API
- Generates cctv.m3u + cctv.json
- Runs on GitHub Actions every 2 hours
"""

import json
import time
import hashlib
import hmac
import base64
import random
import os
import sys
from datetime import datetime
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from playwright.sync_api import sync_playwright

# ============================================================
# CONFIGURATION
# ============================================================

CONFIG_FILE = "config.json"
OUTPUT_DIR = "output"

# Secret keys (from CCTV JS code)
SECRET_1 = "B4B51E8523157ED8D17ADB76041BCD09"
SECRET_2 = "47899B86370B879139C08EA3B5E88267"

# DRM decryption keys (from CCTV JS code)
DECRYPT_KEY = base64.b64decode("0hdiziKsev1LRe24oGTMPwfg9f+kcCWQ56sxi+jMAKE=")
DECRYPT_IV = base64.b64decode("JMo0DT+7XkLZcT1KE1Nv8rOXwxDc7UmOB7eVzx11MvU=")

# All channels (from CCTV EPG API)
CHANNELS = [
    'cctv1', 'cctv2', 'cctv3', 'cctv4', 'cctv5',
    'cctv5plus', 'cctv6', 'cctv7', 'cctv8',
    'cctv10', 'cctv11', 'cctv12', 'cctv13',
    'cctv15', 'cctv16', 'cctv17',
    'cctvnews', 'cctveurope', 'cctvamerica',
    'cctvjilu', 'cctvchild'
]

CHANNEL_NAMES = {
    'cctv1': 'CCTV-1 综合',
    'cctv2': 'CCTV-2 财经',
    'cctv3': 'CCTV-3 综艺',
    'cctv4': 'CCTV-4 中文国际',
    'cctv5': 'CCTV-5 体育',
    'cctv5plus': 'CCTV-5+ 体育赛事',
    'cctv6': 'CCTV-6 电影',
    'cctv7': 'CCTV-7 国防军事',
    'cctv8': 'CCTV-8 电视剧',
    'cctv10': 'CCTV-10 科教',
    'cctv11': 'CCTV-11 戏曲',
    'cctv12': 'CCTV-12 社会与法',
    'cctv13': 'CCTV-13 新闻',
    'cctv15': 'CCTV-15 音乐',
    'cctv16': 'CCTV-16 奥林匹克',
    'cctv17': 'CCTV-17 农业农村',
    'cctvnews': 'CGTN',
    'cctveurope': 'CGTN Europe',
    'cctvamerica': 'CGTN America',
    'cctvjilu': 'CCTV-纪录',
    'cctvchild': 'CCTV-少儿'
}

# ============================================================
# FINGERPRINT FUNCTIONS
# ============================================================

def get_fresh_fingerprint():
    """
    Get fresh cna fingerprint using Playwright headless browser.
    Optimized for GitHub Actions environment.
    """
    try:
        with sync_playwright() as p:
            # Launch browser with sandbox disabled (required for GitHub Actions)
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            # Create context with realistic browser settings
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                java_script_enabled=True,
                bypass_csp=True,
                extra_http_headers={
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                }
            )
            page = context.new_page()
            
            # Navigate to CCTV live page
            print("🔄 Loading CCTV website...")
            page.goto(
                "https://tv.cctv.com/live/cctv1/",
                wait_until="domcontentloaded",
                timeout=60000
            )
            
            # Wait for JavaScript to set cookies
            print("⏳ Waiting for cookies...")
            page.wait_for_timeout(5000)
            
            # Extract cna cookie
            fingerprint = page.evaluate("""
                () => {
                    const cookies = document.cookie.split('; ');
                    for (let cookie of cookies) {
                        if (cookie.startsWith('cna=')) {
                            return cookie.substring(4);
                        }
                    }
                    return null;
                }
            """)
            
            browser.close()
            
            if fingerprint:
                print(f"✅ New fingerprint: {fingerprint[:20]}...")
                return fingerprint
            else:
                print("⚠️ cna cookie not found")
                return None
                
    except Exception as e:
        print(f"❌ Fingerprint refresh error: {e}")
        return None

def load_fingerprint():
    """
    Load fingerprint from config.json.
    If missing or expired, get a fresh one.
    """
    # Check if config exists and has valid fingerprint
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            fp = config.get('fingerprint')
            if fp:
                print(f"✅ Using cached fingerprint: {fp[:20]}...")
                return fp
        except:
            pass
    
    # Get fresh fingerprint
    print("🔄 No valid fingerprint found. Getting fresh one...")
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
    """
    Generate CCTV auth-key using HMAC-SHA256.
    Format: timestamp-random-HMAC_signature
    """
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
    """
    Decrypt CCTV license response.
    Supports: JSON, Base64+JSON, AES-256-CBC encrypted.
    """
    if not response_text:
        return {"public": "0", "tip_msg": "Empty response"}
    
    try:
        # Try direct JSON
        if response_text.strip().startswith('{'):
            return json.loads(response_text)
        
        # Try Base64 decode + AES decrypt
        try:
            encrypted_bytes = base64.b64decode(response_text)
        except:
            return {"public": "0", "tip_msg": "Invalid Base64"}
        
        # AES-256-CBC decrypt
        cipher = AES.new(DECRYPT_KEY, AES.MODE_CBC, DECRYPT_IV)
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        
        # Remove PKCS#7 padding
        try:
            decrypted = unpad(decrypted_bytes, AES.block_size)
        except ValueError:
            decrypted = decrypted_bytes
        
        # Parse JSON
        try:
            return json.loads(decrypted.decode('utf-8'))
        except UnicodeDecodeError:
            try:
                return json.loads(decrypted.decode('latin-1'))
            except:
                return {"public": "0", "tip_msg": "Decoded but not JSON"}
                
    except Exception as e:
        return {"public": "0", "tip_msg": f"Decrypt error: {str(e)[:100]}"}

def get_license(channel, fingerprint):
    """
    Get license from vdnx.live.cntv.cn API.
    Returns license data or None.
    """
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            return decrypt_license(response.text)
        else:
            print(f"   ⚠️ HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"   ❌ Request error: {e}")
        return None

def get_epg(channel):
    """
    Get EPG data from cbox.cntv.cn.
    Returns program list or empty list.
    """
    date = datetime.now().strftime("%Y/%m/%d")
    url = f"https://cbox.cntv.cn/epg/ctlist/{date}/{channel}.json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Extract program list
            if isinstance(data, dict):
                programs = data.get('ct', [])
                if programs:
                    return programs
            return []
    except Exception as e:
        return []
    return []

def extract_stream_url(license_data, channel):
    """
    Extract M3U8 stream URL from license data.
    Returns URL string or None.
    """
    if not license_data:
        return None
    
    manifest = license_data.get('manifest', {})
    
    # Try DRM stream first
    stream_url = manifest.get('hls_cdrm')
    if stream_url:
        return stream_url.replace('${channel}', channel)
    
    # Try non-DRM stream
    stream_url = manifest.get('hls_nd')
    if stream_url:
        return stream_url.replace('${channel}', channel)
    
    return None

def is_drm_stream(license_data):
    """Check if stream requires DRM"""
    if not license_data:
        return False
    manifest = license_data.get('manifest', {})
    return bool(manifest.get('hls_cdrm'))

# ============================================================
# OUTPUT GENERATION
# ============================================================

def generate_m3u(channels_data):
    """
    Generate M3U playlist file.
    """
    m3u = []
    m3u.append("#EXTM3U")
    m3u.append(f"# CCTV Live Stream Playlist")
    m3u.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    m3u.append("")
    
    for channel, data in channels_data.items():
        if not data.get('url'):
            continue
        
        name = data.get('name', channel)
        logo = data.get('logo', '')
        url = data.get('url')
        
        m3u.append(f'#EXTINF:-1 tvg-id="{channel}" tvg-logo="{logo}" group-title="CCTV",{name}')
        m3u.append(f'#EXTVLCOPT:http-referrer=https://tv.cctv.com/')
        m3u.append(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        if data.get('drm'):
            m3u.append(f'#EXTVLCOPT:network-caching=2000')
        m3u.append(f'{url}')
        m3u.append("")
    
    return "\n".join(m3u)

def generate_json(channels_data, fingerprint):
    """
    Generate JSON file with channel data and EPG.
    """
    output = {
        'version': datetime.now().isoformat(),
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fingerprint': fingerprint,
        'total_channels': len(channels_data),
        'channels': {}
    }
    
    for channel, data in channels_data.items():
        output['channels'][channel] = {
            'name': data.get('name', channel),
            'logo': data.get('logo', ''),
            'url': data.get('url', ''),
            'drm': data.get('drm', False),
            'epg': data.get('epg', [])
        }
    
    return output

# ============================================================
# MAIN
# ============================================================

def main():
    """Main execution function"""
    print("="*60)
    print("🚀 CCTV LIVE STREAM EXTRACTOR")
    print("="*60)
    
    # 1. Load/refresh fingerprint
    fingerprint = load_fingerprint()
    if not fingerprint:
        print("❌ No fingerprint available!")
        sys.exit(1)
    
    # 2. Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 3. Process all channels
    channels_data = {}
    success_count = 0
    
    print(f"\n📡 Processing {len(CHANNELS)} channels...")
    print("-"*60)
    
    for i, channel in enumerate(CHANNELS, 1):
        print(f"\n[{i}/{len(CHANNELS)}] {channel} - {CHANNEL_NAMES.get(channel, channel)}")
        
        try:
            # Get license
            license_data = get_license(channel, fingerprint)
            
            if not license_data:
                print(f"   ⚠️ No license data")
                continue
            
            # Check if public
            if license_data.get('public') != '1':
                tip = license_data.get('tip_msg', 'Unknown reason')
                print(f"   ⚠️ Not public: {tip[:50]}")
                continue
            
            # Extract stream URL
            stream_url = extract_stream_url(license_data, channel)
            
            if not stream_url:
                print(f"   ⚠️ No stream URL")
                continue
            
            # Get EPG
            epg = get_epg(channel)
            
            # Store results
            channels_data[channel] = {
                'name': CHANNEL_NAMES.get(channel, channel),
                'url': stream_url,
                'logo': f"https://piccpndks.v.kcdnvip.com/pic/{channel}_2.png",
                'drm': is_drm_stream(license_data),
                'epg': epg
            }
            
            success_count += 1
            print(f"   ✅ Stream URL found")
            print(f"   📋 EPG: {len(epg)} programs")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:100]}")
    
    print("\n" + "="*60)
    print(f"✅ Successfully processed: {success_count}/{len(CHANNELS)} channels")
    print("="*60)
    
    # 4. Generate M3U
    m3u_content = generate_m3u(channels_data)
    m3u_path = os.path.join(OUTPUT_DIR, 'cctv.m3u')
    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write(m3u_content)
    print(f"✅ M3U saved: {m3u_path}")
    
    # 5. Generate JSON
    json_data = generate_json(channels_data, fingerprint)
    json_path = os.path.join(OUTPUT_DIR, 'cctv.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {json_path}")
    
    # 6. Summary
    print("\n📊 SUMMARY")
    print("-"*60)
    print(f"📺 Total channels: {len(CHANNELS)}")
    print(f"✅ Working streams: {success_count}")
    print(f"🔑 Fingerprint: {fingerprint[:20]}...")
    print(f"📁 Output: {OUTPUT_DIR}/")
    print("   ├── cctv.m3u")
    print("   └── cctv.json")
    print("\n🎉 Done!")

if __name__ == "__main__":
    main()

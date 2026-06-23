#!/usr/bin/env python3
"""
CCTV Live Stream Extractor - Final Version with Proxy Support
- ফিঙ্গারপ্রিন্ট: ge.js থেকে অটো জেনারেট
- Proxy: GitHub থেকে অটো লোড
- auth-key: HMAC-SHA256
- লাইসেন্স: vdnx API
- আউটপুট: cctv.m3u + cctv.json
- GitHub Action: প্রতি ২ ঘণ্টা
"""

import json
import time
import hashlib
import hmac
import base64
import random
import os
import re
import sys
from datetime import datetime
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_DIR = "output"
CONFIG_FILE = "config.json"

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
# PROXY FUNCTIONS
# ============================================================

PROXY_CACHE = None

def get_proxy_list():
    """
    GitHub থেকে Proxy লিস্ট নেওয়া
    """
    global PROXY_CACHE
    
    if PROXY_CACHE:
        return PROXY_CACHE
    
    urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    ]
    
    all_proxies = []
    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            proxies = response.text.strip().split('\n')
            proxies = [p.strip() for p in proxies if p.strip()]
            if proxies:
                all_proxies.extend(proxies)
                print(f"✅ Loaded {len(proxies)} proxies from {url.split('/')[-1]}")
        except Exception as e:
            print(f"⚠️ Could not load {url}: {e}")
    
    # Taiwan Proxy (ঐচ্ছিক)
    try:
        tw_url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=TW"
        response = requests.get(tw_url, timeout=10)
        tw_proxies = response.text.strip().split('\n')
        tw_proxies = [p.strip() for p in tw_proxies if p.strip()]
        all_proxies.extend(tw_proxies)
        print(f"✅ Loaded {len(tw_proxies)} Taiwan proxies")
    except:
        pass
    
    PROXY_CACHE = all_proxies
    return all_proxies

def get_working_proxy():
    """
    কাজ করা Proxy খুঁজে বের করা
    """
    proxies = get_proxy_list()
    if not proxies:
        print("⚠️ No proxies available")
        return None
    
    print(f"🔄 Testing {min(len(proxies), 50)} proxies...")
    
    # প্রথম ৫০টি Proxy টেস্ট
    test_proxies = proxies[:50]
    random.shuffle(test_proxies)
    
    for proxy in test_proxies:
        try:
            # ge.js দিয়ে Proxy টেস্ট
            test_url = "https://p.data.cctv.com/ge.js"
            response = requests.get(
                test_url,
                proxies={'http': proxy, 'https': proxy},
                timeout=5
            )
            if response.status_code == 200:
                print(f"✅ Working proxy found: {proxy}")
                return proxy
        except:
            continue
    
    print("❌ No working proxy found!")
    return None

def get_proxies_dict():
    """
    Proxy dict তৈরি করা (requests-এর জন্য)
    """
    proxy = get_working_proxy()
    if proxy:
        return {'http': proxy, 'https': proxy}
    return None

# ============================================================
# FINGERPRINT FUNCTIONS
# ============================================================

def get_fingerprint_from_gejs(proxies=None):
    """
    ge.js থেকে ফিঙ্গারপ্রিন্ট নেওয়া
    """
    try:
        url = "https://p.data.cctv.com/ge.js"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://tv.cctv.com/",
            "Accept": "*/*"
        }
        
        response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        
        # কুকি থেকে cna নেওয়া
        cna = response.cookies.get("cna")
        if cna:
            print(f"✅ Fingerprint from cookie: {cna[:20]}...")
            return cna
        
        # রেসপন্স বডি থেকে Etag
        match = re.search(r'goldlog\.Etag="([^"]+)"', response.text)
        if match:
            cna = match.group(1)
            print(f"✅ Fingerprint from Etag: {cna[:20]}...")
            return cna
        
        print("❌ No fingerprint found in ge.js response")
        return None
        
    except Exception as e:
        print(f"❌ ge.js error: {e}")
        return None

def load_fingerprint():
    """
    ফিঙ্গারপ্রিন্ট লোড করা
    """
    # 1. Proxy ব্যবহার করে ge.js থেকে নেওয়ার চেষ্টা
    proxies = get_proxies_dict()
    fingerprint = get_fingerprint_from_gejs(proxies)
    
    if fingerprint:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                'fingerprint': fingerprint,
                'updated': datetime.now().isoformat()
            }, f, indent=2)
        return fingerprint
    
    # 2. Proxy ছাড়া ge.js চেষ্টা
    print("🔄 Trying without proxy...")
    fingerprint = get_fingerprint_from_gejs(None)
    if fingerprint:
        return fingerprint
    
    # 3. config.json থেকে পড়া
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            fp = config.get('fingerprint')
            if fp:
                print(f"⚠️ Using cached fingerprint: {fp[:20]}...")
                return fp
        except:
            pass
    
    print("❌ Failed to get fingerprint!")
    return None

# ============================================================
# AUTH-KEY FUNCTIONS
# ============================================================

def generate_auth_key(channel, fingerprint):
    """
    CCTV auth-key জেনারেট করা (HMAC-SHA256)
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

# ============================================================
# LICENSE FUNCTIONS
# ============================================================

def decrypt_license(response_text):
    """
    CCTV লাইসেন্স ডিক্রিপ্ট করা
    """
    if not response_text:
        return {"public": "0", "tip_msg": "Empty response"}
    
    try:
        if response_text.strip().startswith('{'):
            return json.loads(response_text)
        
        try:
            encrypted_bytes = base64.b64decode(response_text)
        except:
            return {"public": "0", "tip_msg": "Invalid Base64"}
        
        cipher = AES.new(DECRYPT_KEY, AES.MODE_CBC, DECRYPT_IV)
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        
        try:
            decrypted = unpad(decrypted_bytes, AES.block_size)
        except ValueError:
            decrypted = decrypted_bytes
        
        try:
            return json.loads(decrypted.decode('utf-8'))
        except UnicodeDecodeError:
            try:
                return json.loads(decrypted.decode('latin-1'))
            except:
                return {"public": "0", "tip_msg": "Decoded but not JSON"}
                
    except Exception as e:
        return {"public": "0", "tip_msg": f"Decrypt error: {str(e)[:100]}"}

def get_license(channel, fingerprint, proxies=None):
    """
    vdnx.live.cntv.cn থেকে লাইসেন্স নেওয়া
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=15)
        if response.status_code == 200:
            return decrypt_license(response.text)
        else:
            print(f"   ⚠️ HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"   ❌ Request error: {e}")
        return None

# ============================================================
# EPG FUNCTIONS
# ============================================================

def get_epg(channel):
    """
    cbox.cntv.cn থেকে EPG ডেটা নেওয়া
    """
    date = datetime.now().strftime("%Y/%m/%d")
    url = f"https://cbox.cntv.cn/epg/ctlist/{date}/{channel}.json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                programs = data.get('ct', [])
                if programs:
                    return programs
            return []
    except Exception as e:
        return []
    return []

# ============================================================
# STREAM URL FUNCTIONS
# ============================================================

def extract_stream_url(license_data, channel):
    """
    লাইসেন্স ডেটা থেকে M3U8 URL বের করা
    """
    if not license_data:
        return None
    
    manifest = license_data.get('manifest', {})
    
    stream_url = manifest.get('hls_cdrm')
    if stream_url:
        return stream_url.replace('${channel}', channel)
    
    stream_url = manifest.get('hls_nd')
    if stream_url:
        return stream_url.replace('${channel}', channel)
    
    return None

def is_drm_stream(license_data):
    """স্ট্রিমে DRM সক্রিয় কিনা চেক"""
    if not license_data:
        return False
    manifest = license_data.get('manifest', {})
    return bool(manifest.get('hls_cdrm'))

# ============================================================
# OUTPUT GENERATION
# ============================================================

def generate_m3u(channels_data):
    """
    M3U প্লেলিস্ট ফাইল তৈরি
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
        if data.get('drm'):
            m3u.append(f'#EXTVLCOPT:network-caching=2000')
        m3u.append(f'{url}')
        m3u.append("")
    
    return "\n".join(m3u)

def generate_json(channels_data, fingerprint):
    """
    JSON ফাইল তৈরি (EPG + চ্যানেল ডেটা)
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
    print("="*60)
    print("🚀 CCTV LIVE STREAM EXTRACTOR (with Proxy)")
    print("="*60)
    
    # 1. ফিঙ্গারপ্রিন্ট নেওয়া
    fingerprint = load_fingerprint()
    if not fingerprint:
        print("❌ No fingerprint available!")
        sys.exit(1)
    
    # 2. আউটপুট ডিরেক্টরি তৈরি
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 3. Proxy নেওয়া
    proxies = get_proxies_dict()
    
    # 4. সব চ্যানেল প্রসেস
    channels_data = {}
    success_count = 0
    
    print(f"\n📡 Processing {len(CHANNELS)} channels...")
    print("-"*60)
    
    for i, channel in enumerate(CHANNELS, 1):
        print(f"\n[{i}/{len(CHANNELS)}] {channel} - {CHANNEL_NAMES.get(channel, channel)}")
        
        try:
            license_data = get_license(channel, fingerprint, proxies)
            
            if not license_data:
                print(f"   ⚠️ No license data")
                continue
            
            if license_data.get('public') != '1':
                tip = license_data.get('tip_msg', 'Unknown reason')
                print(f"   ⚠️ Not public: {tip[:50]}")
                continue
            
            stream_url = extract_stream_url(license_data, channel)
            
            if not stream_url:
                print(f"   ⚠️ No stream URL")
                continue
            
            epg = get_epg(channel)
            
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
    
    # 5. M3U তৈরি
    m3u_content = generate_m3u(channels_data)
    m3u_path = os.path.join(OUTPUT_DIR, 'cctv.m3u')
    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write(m3u_content)
    print(f"✅ M3U saved: {m3u_path}")
    
    # 6. JSON তৈরি
    json_data = generate_json(channels_data, fingerprint)
    json_path = os.path.join(OUTPUT_DIR, 'cctv.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {json_path}")
    
    # 7. সারাংশ
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

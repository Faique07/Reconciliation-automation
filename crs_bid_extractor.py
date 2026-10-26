import pandas as pd
import requests
import json
import re
import time
import difflib
from datetime import datetime, timedelta
import os
import sys
import tkinter as tk
from tkinter import filedialog

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

# ==========================================
# CONFIGURATION
# ==========================================
API_URL = "https://crs.fabhotels.com/admin/crs/fabcrs/booking/search" 
DETAILS_API_URL = "https://crs.fabhotels.com/admin/crs/fabcrs/booking/get/"
# ==========================================

def get_tokens_via_browser():
    print("\n[+] Opening Chrome browser for Login...")
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = None
    
    # 1. Try Selenium's built-in driver management (Selenium 4.6+)
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e1:
        print(f"[-] Selenium Manager attempt: {e1}")
        
        # Remove any stale lock file in ~/.wdm if present
        lock_file = os.path.expanduser(r"~/.wdm/.wdm-lock-chromedriver-win64")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
        
        # 2. Try ChromeDriverManager fallback
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e2:
            print(f"[-] ChromeDriverManager attempt failed: {e2}")
            
            # 3. Try standard Chrome executable paths if binary location wasn't found
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
            ]
            for cp in chrome_paths:
                if os.path.exists(cp):
                    try:
                        options.binary_location = cp
                        driver = webdriver.Chrome(options=options)
                        break
                    except Exception:
                        pass

    if not driver:
        print("\n[!] Error: Unable to launch Google Chrome.")
        print("Please ensure:")
        print("  1. Google Chrome is installed on your computer.")
        print("  2. Your internet connection is active.")
        return None, None
        
    interceptor_script = """
    const origSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
        if (header.toLowerCase() === 'tenant-token') {
            localStorage.setItem('found-tenant-token', value); 
        }
        origSetRequestHeader.apply(this, arguments);
    };
    
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        if (args[1] && args[1].headers) {
            let tt = null;
            if (args[1].headers instanceof Headers) {
                tt = args[1].headers.get('tenant-token');
            } else {
                tt = args[1].headers['tenant-token'] || args[1].headers['Tenant-Token'];
            }
            if (tt) {
                localStorage.setItem('found-tenant-token', tt);
            }
        }
        return originalFetch.apply(this, args);
    };
    """
    
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': interceptor_script})
    
    driver.get("https://crs.fabhotels.com/admin/crs/booking/search")
    
    print("="*60)
    print("  PLEASE LOG IN TO THE OPENED BROWSER WINDOW.")
    print("  Wait for the 'Search Bookings' page to load completely.")
    print("  DO NOT CLOSE THE BROWSER. IT WILL CLOSE AUTOMATICALLY.")
    print("="*60)
    
    token = None
    tenant_token = None
    
    try:
        timeout = time.time() + 300 
        while time.time() < timeout:
            if not token:
                cookies = driver.get_cookies()
                for cookie in cookies:
                    if cookie['name'] == 'token':
                        token = cookie['value']
                        print(f"  [+] Found 'token' cookie!")
            
            if not tenant_token and token:
                try:
                    script = """
                    var result = {};
                    for (var i = 0; i < localStorage.length; i++) {
                        var key = localStorage.key(i);
                        result['LS:' + key] = localStorage.getItem(key);
                    }
                    for (var i = 0; i < sessionStorage.length; i++) {
                        var key = sessionStorage.key(i);
                        result['SS:' + key] = sessionStorage.getItem(key);
                    }
                    return result;
                    """
                    all_storage = driver.execute_script(script)
                    
                    for k, v in all_storage.items():
                        if 'tenant' in k.lower():
                            uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', str(v), re.I)
                            if uuids:
                                tenant_token = uuids[0]
                                break
                            elif isinstance(v, str) and len(v) > 10:
                                tenant_token = v.strip('"\'')
                                break
                                
                    if not tenant_token:
                        for k, v in all_storage.items():
                            uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', str(v), re.I)
                            for uid in uuids:
                                if uid != token:
                                    tenant_token = uid
                                    break
                            if tenant_token: break
                            
                except Exception as ex:
                    pass
                
            if token and tenant_token:
                print("\n[✔] Both tokens successfully extracted! Closing browser in 2 seconds...")
                time.sleep(2) 
                break
                
            time.sleep(2)
            
    except Exception as e:
        print(f"\nBrowser was closed or connection lost: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass
        
    return token, tenant_token


def clean_name(name):
    if pd.isna(name):
        return set()
    name_spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(name))
    cleaned = re.sub(r'[^a-z0-9]', ' ', name_spaced.lower())
    words = cleaned.split()
    NOISE = {'thank', 'thanks', 'hotel', 'guest', 'shri', 'smt'}
    return set([w for w in words if w not in NOISE])


def match_names(name1, name2):
    set1 = clean_name(name1)
    set2 = clean_name(name2)
    
    if not set1 or not set2:
        return False
        
    if set1.issubset(set2) or set2.issubset(set1):
        return True
        
    COMMON_WORDS = {'mr', 'mrs', 'ms', 'dr', 'md', 'mohd', 'kumar', 'singh', 'sharma', 'patel', 'das', 'gupta', 'yadav', 'devi', 'prasad', 'ali', 'khan', 'ahmed', 'shaikh'}
    intersection = set1.intersection(set2)
    if intersection:
        valid_words = [w for w in intersection if w not in COMMON_WORDS and len(w) >= 3]
        if valid_words:
            return True
            
    # Prefix matching for truncated names (e.g., 'choudha' vs 'choudhary')
    for w1 in set1:
        if w1 in COMMON_WORDS or len(w1) < 4:
            continue
        for w2 in set2:
            if w2 in COMMON_WORDS or len(w2) < 4:
                continue
            if w1.startswith(w2) or w2.startswith(w1):
                return True
                
    # Fuzzy string matching for spelling variations and typos (e.g. 'sahrma' vs 'sharma', 'pooja' vs 'puja')
    for w1 in set1:
        if w1 in COMMON_WORDS or len(w1) < 4:
            continue
        for w2 in set2:
            if w2 in COMMON_WORDS or len(w2) < 4:
                continue
            if difflib.SequenceMatcher(None, w1, w2).ratio() >= 0.82:
                return True
                
    return False


def parse_date(date_str):
    if pd.isna(date_str):
        return None
    try:
        if isinstance(date_str, datetime):
            return date_str.date()
        if isinstance(date_str, pd.Timestamp):
            return date_str.date()
            
        return pd.to_datetime(date_str, dayfirst=True).date()
    except:
        return None


def extract_all_dates(date_val):
    if pd.isna(date_val):
        return []
        
    dates = []
    
    # 1. Handle datetime / Timestamp (Excel may have parsed D/M/YYYY into US M/D/YYYY)
    if isinstance(date_val, (datetime, pd.Timestamp)):
        d = date_val.date()
        dates.append(d)
        if d.day <= 12 and d.day != d.month:
            try:
                dates.append(datetime(d.year, d.day, d.month).date())
            except ValueError:
                pass
        return dates
        
    date_str = str(date_val).strip()
    if not date_str or date_str.isdigit():
        return []
        
    clean_str = re.sub(r'\([^)]*\)', '', date_str).strip()
    
    # 2. Try parsing string as single date
    try:
        parsed = pd.to_datetime(clean_str, dayfirst=True).date()
        dates.append(parsed)
        if parsed.day <= 12 and parsed.day != parsed.month:
            try:
                dates.append(datetime(parsed.year, parsed.day, parsed.month).date())
            except ValueError:
                pass
        return dates
    except Exception:
        pass
        
    # 3. Handle date range strings (e.g. '01/09/2026 - 02/09/2026')
    splitters = [' - ', ' to ', '...', ' to']
    parts = []
    for splitter in splitters:
        if splitter in clean_str:
            parts = clean_str.split(splitter)
            break
            
    if not parts and '-' in clean_str:
        parts = [p for p in clean_str.split('-') if len(p.strip()) >= 5]
        
    if parts:
        for p in parts:
            try:
                parsed = pd.to_datetime(p.strip(), dayfirst=True).date()
                dates.append(parsed)
                if parsed.day <= 12 and parsed.day != parsed.month:
                    try:
                        dates.append(datetime(parsed.year, parsed.day, parsed.month).date())
                    except ValueError:
                        pass
            except Exception:
                pass
                
    return dates


def fetch_crs_data(session, pid, token, tenant_token, fname, lname, cache=None):
    cache_key = (str(pid), str(fname).strip().lower(), str(lname).strip().lower())
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json;charset=UTF-8',
        'cookie': f'token={token}', 
        'origin': 'https://crs.fabhotels.com',
        'tenant-token': f'{tenant_token}',
        'token': f'{token}',
        'uri': 'admin/bookingsservice/admin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    payload = {
        "bookingSearchRequestDto": {
            "pageNo": 1,
            "limit": 200, 
            "firstName": fname,
            "lastName": lname,
            "propertyId": str(pid),
            "bookingStatus": -1,
            "guestStatus": -1,
            "oldSearch": False
        }
    }
    try:
        response = session.post(API_URL, headers=headers, json=payload, timeout=12)
        if response.status_code == 200:
            data = response.json().get('data')
            result = data if data else []
            if cache is not None:
                cache[cache_key] = result
            return result
    except Exception:
        pass
        
    if cache is not None:
        cache[cache_key] = []
    return []


def fetch_booking_details(session, bid, token, tenant_token, cache=None):
    if cache is not None and bid in cache:
        return cache[bid]

    url = f"{DETAILS_API_URL}{bid}"
    headers = {
        'accept': 'application/json, text/plain, */*',
        'cookie': f'token={token}', 
        'tenant-token': f'{tenant_token}',
        'token': f'{token}',
        'uri': 'admin/bookingsservice/update',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    try:
        response = session.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            data = response.json().get('data', {})
            details = data.get('travellerDetails', [])
            if cache is not None:
                cache[bid] = details
            return details
    except Exception:
        pass
        
    if cache is not None:
        cache[bid] = []
    return []


def find_columns(df):
    guest_col = None
    date_cols = []
    
    for col in df.columns:
        col_lower = str(col).lower()
        if 'guest' in col_lower:
            guest_col = col
            break
            
    if not guest_col:
        for col in df.columns:
            col_lower = str(col).lower()
            if 'name' in col_lower and 'company' not in col_lower:
                guest_col = col
                break

    for col in df.columns:
        col_lower = str(col).lower().replace(' ', '')
        # Exclude duration/night count columns
        if 'night' in col_lower:
            continue
        if any(keyword in col_lower for keyword in ['c/in', 'cin', 'checkin', 'c/out', 'cout', 'c/o', 'checkout', 'date']):
            date_cols.append(col)
                
    return guest_col, date_cols


def process_ledger(excel_path, pid, token, tenant_token):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=2)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    search_cache = {}
    details_cache = {}

    print(f"\nReading Excel file: {excel_path}")
    try:
        df = pd.read_excel(excel_path)
        guest_col, date_cols = find_columns(df)
        
        if not guest_col or not date_cols:
            df = pd.read_excel(excel_path, header=None)
            header_idx = -1
            for i, row in df.head(15).iterrows():
                row_str = " ".join([str(x).lower() for x in row.values])
                if ('guest' in row_str or 'name' in row_str) and ('date' in row_str or 'check' in row_str or 'cin' in row_str or 'cout' in row_str):
                    header_idx = i
                    break
                    
            if header_idx != -1:
                df.columns = df.iloc[header_idx]
                df = df.iloc[header_idx + 1:].reset_index(drop=True)
                guest_col, date_cols = find_columns(df)
                
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    if not guest_col or not date_cols:
        print("Could not automatically identify columns. Please ensure columns have 'name'/'guest' and 'date'/'checkout' in their headers.")
        return
        
    print(f"Identified Guest Column: '{guest_col}'")
    print(f"Identified Date Columns: {date_cols}")

    df['BID'] = "NOT FOUND"
    total_rows = len(df)
    
    COMMON_TITLES = {'mr', 'mrs', 'ms', 'dr', 'md', 'mohd', 'thank', 'thanks', 'hotel', 'guest', 'shri', 'smt'}
    COMMON_SURNAMES = {'kumar', 'singh', 'sharma', 'patel', 'das', 'gupta', 'yadav', 'devi', 'prasad', 'ali', 'khan', 'ahmed', 'shaikh'}

    print(f"\nProcessing {total_rows} ledger rows...")
    for index, row in df.iterrows():
        ledger_name_raw = row[guest_col]
        
        if pd.isna(ledger_name_raw):
            continue
            
        ledger_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(ledger_name_raw).strip())
        
        ledger_dates = []
        for d_col in date_cols:
            extracted = extract_all_dates(row[d_col])
            if extracted:
                ledger_dates.extend(extracted)
        
        if not ledger_dates:
            continue
            
        print(f"\n[{index+1}/{total_rows}] Checking Guest: '{ledger_name}'")
        
        ledger_name_clean = re.sub(r'[^a-zA-Z0-9]', ' ', str(ledger_name))
        raw_words = [p.strip() for p in ledger_name_clean.split() if len(p.strip()) > 0]
        
        # Filter leading noise words like "Thank" from ledger name
        all_words = []
        for i, w in enumerate(raw_words):
            if i == 0 and w.lower() in {'thank', 'thanks', 'hotel', 'guest', 'shri', 'smt'}:
                continue
            all_words.append(w)
        if not all_words:
            all_words = raw_words
            
        clean_full_name = " ".join(all_words)
        
        search_combinations = []
        # 1. Full name in First Name (matches manual CRS UI search)
        search_combinations.append((clean_full_name, ""))
        
        # 2. First and Last Name split if 2+ words
        if len(all_words) >= 2:
            search_combinations.append((all_words[0], " ".join(all_words[1:])))
            search_combinations.append((all_words[0], all_words[-1]))
            
        # 3. Full name in Last Name
        search_combinations.append(("", clean_full_name))
        
        # 4. First name only / Last name combinations (avoid standalone common surnames)
        if len(all_words) >= 2:
            if all_words[0].lower() not in COMMON_SURNAMES and len(all_words[0]) >= 3:
                search_combinations.append((all_words[0], ""))
            if all_words[-1].lower() not in COMMON_SURNAMES and len(all_words[-1]) >= 3:
                search_combinations.append((all_words[-1], ""))
            search_combinations.append((all_words[-1], all_words[0]))
            
        # 5. Significant individual distinctive words (skip common titles and common surnames)
        search_words = [w for w in all_words if w.lower() not in COMMON_TITLES and w.lower() not in COMMON_SURNAMES and len(w) >= 3]
        for word in sorted(search_words, key=len, reverse=True):
            search_combinations.append((word, ""))
            search_combinations.append(("", word))
            
        # If no combinations were generated (e.g. name only consists of common surnames):
        if not search_combinations:
            if len(all_words) >= 2:
                search_combinations.append((all_words[0], all_words[-1]))
            for w in all_words:
                if len(w) >= 3:
                    search_combinations.append((w, ""))
                
        seen_combos = set()
        unique_combinations = []
        for combo in search_combinations:
            if combo not in seen_combos:
                seen_combos.add(combo)
                unique_combinations.append(combo)
                
        valid_matches = []
        seen_bids = set()
        
        for fname_search, lname_search in unique_combinations:
            crs_data = fetch_crs_data(session, pid, token, tenant_token, fname_search, lname_search, search_cache)
            
            for crs_record in crs_data:
                bid = crs_record.get('bookingId')
                if not bid or bid in seen_bids:
                    continue
                seen_bids.add(bid)
                
                crs_checkin_raw = crs_record.get('checkIn', '')
                crs_checkout_raw = crs_record.get('checkOut', '')
                
                crs_checkin_date = parse_date(crs_checkin_raw)
                crs_checkout_date = parse_date(crs_checkout_raw) 
                
                if not crs_checkin_date or not crs_checkout_date:
                    continue
                
                # --- SPEED CRITICAL: DATE PROXIMITY CHECK FIRST ---
                # Check date distance in-memory BEFORE calling any external API
                min_days_dist = 9999
                best_date_score = None
                for l_date in ledger_dates:
                    if crs_checkin_date <= l_date <= crs_checkout_date:
                        dist = 0
                    elif l_date < crs_checkin_date:
                        dist = (crs_checkin_date - l_date).days
                    else:
                        dist = (l_date - crs_checkout_date).days
                        
                    is_exact_co = (l_date == crs_checkout_date)
                    is_inside = (crs_checkin_date <= l_date <= crs_checkout_date)
                    dist_to_ci = abs((l_date - crs_checkin_date).days)
                    dist_to_co = abs((l_date - crs_checkout_date).days)
                    min_dist_to_edge = min(dist_to_ci, dist_to_co)
                    
                    if dist <= 3:
                        tier = 0
                    elif dist <= 7:
                        tier = 1
                    else:
                        tier = 2
                        
                    date_score = (tier, not is_exact_co, not is_inside, dist, min_dist_to_edge)
                    if best_date_score is None or date_score < best_date_score:
                        best_date_score = date_score
                        min_days_dist = dist
                        
                # If booking dates are more than 7 days away from ledger dates, it CANNOT be this booking!
                # Skipping here in memory avoids hundreds of slow HTTP calls!
                if min_days_dist > 7:
                    continue
                
                # STEP 1: Name Match (Primary Guest)
                crs_first_name = crs_record.get('firstName', '')
                crs_last_name = crs_record.get('lastName', '')
                crs_full_name = f"{crs_first_name} {crs_last_name}".strip()
                
                name_matches = match_names(clean_full_name, crs_full_name)
                matched_name_str = crs_full_name
                
                # STEP 2: Deep Search (Secondary Guests)
                # ONLY fetch details for secondary guests if dates match AND primary name did not match
                if not name_matches:
                    secondary_guests = fetch_booking_details(session, bid, token, tenant_token, details_cache)
                    for guest in secondary_guests:
                        sec_fname = guest.get('firstName', '')
                        sec_lname = guest.get('lastName', '')
                        sec_full_name = f"{sec_fname} {sec_lname}".strip()
                        
                        if match_names(clean_full_name, sec_full_name):
                            name_matches = True
                            matched_name_str = sec_full_name  
                            break
                            
                if not name_matches:
                    continue
                    
                valid_matches.append({
                    'record': crs_record,
                    'full_name': matched_name_str,
                    'bid': bid,
                    'score': best_date_score
                })
            
            # If we found high-confidence (tier 0) date match, stop querying other combinations
            if any(m['score'][0] == 0 for m in valid_matches):
                break
                
        if valid_matches:
            valid_matches.sort(key=lambda x: x['score'])
            best_match = valid_matches[0]
            
            bid = best_match['bid']
            df.at[index, 'BID'] = bid
            print(f"  *** MATCH FOUND! {best_match['full_name']} -> BID: {bid} ***")
        else:
            print(f"  --- No match found ---")

    base, _ = os.path.splitext(excel_path)
    output_path = f"{base}_processed.xlsx"
    try:
        df.to_excel(output_path, index=False, engine='openpyxl')
        print(f"\nProcessing complete! Output saved to: {output_path}")
    except Exception as e:
        print(f"Error saving Excel file ({e}). Saving as CSV instead...")
        try:
            csv_path = f"{base}_processed.csv"
            df.to_csv(csv_path, index=False)
            print(f"Output saved to CSV: {csv_path}")
        except Exception as e2:
            print(f"Error saving output file: {e2}")


if __name__ == "__main__":
    print("--- CRs BID Extraction Automation ---")
    
    root = tk.Tk()
    root.withdraw()
    
    pid = input("Enter Property ID (PID): ").strip()
    if not pid:
        print("PID is required!")
        sys.exit()

    token, tenant_token = get_tokens_via_browser()
    
    if not token or not tenant_token:
        print("\nFailed to get tokens automatically.")
        token = input("Enter 'token' manually (or press enter to skip): ").strip()
        tenant_token = input("Enter 'tenant-token' manually (or press enter to skip): ").strip()
        
    if not token or not tenant_token:
         print("Tokens are required. Exiting...")
         sys.exit()

    print("\nPlease select your Excel ledger file from the dialog box...")
    excel_file = filedialog.askopenfilename(
        title="Select Hotel Ledger Excel File",
        filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
    )
    
    if not excel_file:
        print("No file selected. Exiting...")
        sys.exit()
        
    process_ledger(excel_file, pid, token, tenant_token)

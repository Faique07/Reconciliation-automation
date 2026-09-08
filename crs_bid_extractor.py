import pandas as pd
import requests
import json
import re
import time
from datetime import datetime, timedelta
import sys
import tkinter as tk
from tkinter import filedialog

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

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
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"Error starting Chrome: {e}")
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
    # Naya Logic: Handle CamelCase without spaces (PrajapatiBhavesh -> Prajapati Bhavesh)
    name_spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(name))
    cleaned = re.sub(r'[^a-z0-9]', ' ', name_spaced.lower())
    return set(cleaned.split())


def match_names(name1, name2):
    set1 = clean_name(name1)
    set2 = clean_name(name2)
    
    if not set1 or not set2:
        return False
        
    if set1.issubset(set2) or set2.issubset(set1):
        return True
        
    intersection = set1.intersection(set2)
    if intersection:
        COMMON_WORDS = {'mr', 'mrs', 'ms', 'dr', 'md', 'mohd', 'kumar', 'singh', 'sharma', 'patel', 'das', 'gupta', 'yadav', 'devi', 'prasad', 'ali', 'khan', 'ahmed', 'shaikh'}
        valid_words = [w for w in intersection if w not in COMMON_WORDS and len(w) >= 3]
        if valid_words:
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
        
    if isinstance(date_val, datetime):
        return [date_val.date()]
    if isinstance(date_val, pd.Timestamp):
        return [date_val.date()]
        
    date_str = str(date_val).strip()
    
    # Bracket me likhi hui (Nights) value remove karo -> e.g. "(3)"
    clean_str = re.sub(r'\([^)]*\)', '', date_str).strip()
    
    try:
        return [pd.to_datetime(clean_str, dayfirst=True).date()]
    except:
        pass
        
    valid_dates = []
    splitters = [' - ', ' to ', '...', ' to']
    parts = []
    
    for splitter in splitters:
        if splitter in clean_str:
            parts = clean_str.split(splitter)
            break
            
    if not parts and '-' in clean_str:
        # Split by hyphen but only if parts are long enough to be dates
        parts = [p for p in clean_str.split('-') if len(p.strip()) >= 5]
        
    if parts:
        for p in parts:
            try:
                valid_dates.append(pd.to_datetime(p.strip(), dayfirst=True).date())
            except:
                pass
                
    return valid_dates


def fetch_crs_data(pid, token, tenant_token, fname, lname):
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
        response = requests.post(API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json().get('data')
            return data if data else []
    except Exception:
        pass
    return []


def fetch_booking_details(bid, token, tenant_token):
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
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get('data', {})
            return data.get('travellerDetails', [])
    except Exception:
        pass
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
        if any(keyword in col_lower for keyword in ['date', 'c/in', 'cin', 'checkin', 'c/out', 'cout', 'c/o', 'checkout', 'nights']):
            date_cols.append(col)
                
    return guest_col, date_cols


def process_ledger(excel_path, pid, token, tenant_token):
    print(f"\nReading Excel file: {excel_path}")
    try:
        df = pd.read_excel(excel_path)
        guest_col, date_cols = find_columns(df)
        
        # Agar upar empty rows hain toh header neeche shift ho jata hai. Us case me dynamically header dhoondo.
        if not guest_col or not date_cols:
            df = pd.read_excel(excel_path, header=None)
            header_idx = -1
            for i, row in df.head(15).iterrows():
                row_str = " ".join([str(x).lower() for x in row.values])
                if ('guest' in row_str or 'name' in row_str) and ('date' in row_str or 'check' in row_str or 'nights' in row_str):
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
    
    print("\nProcessing ledger rows...")
    for index, row in df.iterrows():
        ledger_name_raw = row[guest_col]
        
        if pd.isna(ledger_name_raw):
            continue
            
        # Naya Logic: CamelCase ko space se alag karna (e.g. PrajapatiBhavesh -> Prajapati Bhavesh)
        ledger_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(ledger_name_raw).strip())
        
        has_checkout = False
        ledger_dates = []
        for d_col in date_cols:
            extracted = extract_all_dates(row[d_col])
            if extracted:
                ledger_dates.extend(extracted)
                col_lower = str(d_col).lower().replace(' ', '')
                if any(k in col_lower for k in ['c/out', 'cout', 'c/o', 'checkout', 'nights']):
                    has_checkout = True
        
        if not ledger_dates:
            continue
            
        print(f"\n[{index+1}] Checking Guest: '{ledger_name}'")
        
        ledger_name_clean = re.sub(r'[^a-zA-Z0-9]', ' ', str(ledger_name))
        valid_words = [p.strip() for p in ledger_name_clean.split() if len(p.strip()) >= 3]
        
        search_combinations = []
        search_combinations.append((ledger_name_clean, ""))
        search_combinations.append(("", ledger_name_clean))
        
        top_words = sorted(valid_words, key=len, reverse=True)[:4]
        if len(top_words) >= 2:
            for i in range(len(top_words)):
                for j in range(len(top_words)):
                    if i != j:
                        search_combinations.append((top_words[i], top_words[j]))
                        
        for word in sorted(valid_words, key=len, reverse=True):
            search_combinations.append((word, ""))
            search_combinations.append(("", word))
            
        seen_combos = set()
        unique_combinations = []
        for combo in search_combinations:
            if combo not in seen_combos:
                seen_combos.add(combo)
                unique_combinations.append(combo)
                
        valid_matches = []
        
        for fname_search, lname_search in unique_combinations:
            crs_data = fetch_crs_data(pid, token, tenant_token, fname_search, lname_search)
            
            for crs_record in crs_data:
                crs_checkin_raw = crs_record.get('checkIn', '')
                crs_checkout_raw = crs_record.get('checkOut', '')
                
                crs_checkin_date = parse_date(crs_checkin_raw)
                crs_checkout_date = parse_date(crs_checkout_raw) 
                
                if not crs_checkin_date or not crs_checkout_date:
                    continue
                
                # STEP 1: Date Match (Naya Score Logic)
                best_sub_score = None
                is_valid_date_overall = False
                matched_dates_count = 0
                
                for l_date in ledger_dates:
                    is_valid_date = False
                    if has_checkout:
                        if crs_checkin_date <= l_date <= crs_checkout_date:
                            is_valid_date = True
                    else:
                        ci_buffer = crs_checkin_date - timedelta(days=2)
                        co_buffer = crs_checkout_date + timedelta(days=2)
                        if ci_buffer <= l_date <= co_buffer:
                            is_valid_date = True
                            
                    if is_valid_date:
                        matched_dates_count += 1
                        is_valid_date_overall = True
                        
                        is_exact_co = (l_date == crs_checkout_date)
                        is_inside = (crs_checkin_date <= l_date <= crs_checkout_date)
                        dist_to_ci = abs((l_date - crs_checkin_date).days)
                        dist_to_co = abs((l_date - crs_checkout_date).days)
                        min_dist = min(dist_to_ci, dist_to_co)
                        
                        sub_score = (not is_exact_co, not is_inside, min_dist, dist_to_co)
                        
                        if best_sub_score is None or sub_score < best_sub_score:
                            best_sub_score = sub_score
                            
                if not is_valid_date_overall:
                    continue
                    
                # Naya tie-breaker: Jiski sabse zyada dates match hongi, wo jeetega (-ve sign for sorting priority)
                best_score = (-matched_dates_count, best_sub_score[0], best_sub_score[1], best_sub_score[2], best_sub_score[3])
                
                # STEP 2: Name Match (Primary Guest)
                crs_first_name = crs_record.get('firstName', '')
                crs_last_name = crs_record.get('lastName', '')
                crs_full_name = f"{crs_first_name} {crs_last_name}".strip()
                
                name_matches = match_names(ledger_name, crs_full_name)
                matched_name_str = crs_full_name
                
                # STEP 3: Deep Search (Secondary Guests)
                if not name_matches:
                    bid = crs_record.get('bookingId')
                    secondary_guests = fetch_booking_details(bid, token, tenant_token)
                    
                    for guest in secondary_guests:
                        sec_fname = guest.get('firstName', '')
                        sec_lname = guest.get('lastName', '')
                        sec_full_name = f"{sec_fname} {sec_lname}".strip()
                        
                        if match_names(ledger_name, sec_full_name):
                            name_matches = True
                            matched_name_str = sec_full_name  
                            break
                            
                if name_matches:
                    valid_matches.append({
                        'record': crs_record,
                        'full_name': matched_name_str,
                        'bid': crs_record.get('bookingId'),
                        'score': best_score
                    })
            
            if valid_matches:
                break
                
        if valid_matches:
            valid_matches.sort(key=lambda x: x['score'])
            best_match = valid_matches[0]
            
            bid = best_match['bid']
            df.at[index, 'BID'] = bid
            print(f"  *** MATCH FOUND! {best_match['full_name']} -> BID: {bid} ***")
        else:
             print(f"  --- No match found ---")

    output_path = excel_path.replace('.xlsx', '_processed.xlsx')
    try:
        df.to_excel(output_path, index=False)
        print(f"\nProcessing complete! Output saved to: {output_path}")
    except Exception as e:
        print(f"Error saving output file: {e}")


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

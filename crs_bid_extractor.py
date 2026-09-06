import pandas as pd
import requests
import json
import re
import time
from datetime import datetime
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
        
    # INJECT NETWORK INTERCEPTOR TO STEAL HIDDEN HEADERS
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
    
    # URL TO DIRECTLY OPEN THE BOOKING PAGE
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
            # 1. Check for token in cookies
            if not token:
                cookies = driver.get_cookies()
                for cookie in cookies:
                    if cookie['name'] == 'token':
                        token = cookie['value']
                        print(f"  [+] Found 'token' cookie!")
            
            # 2. BRUTE FORCE SEARCH FOR TENANT-TOKEN
            if not tenant_token and token:
                try:
                    # Dump all Local Storage and Session Storage
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
                    
                    # Search logic 1: Look for any key containing 'tenant'
                    for k, v in all_storage.items():
                        if 'tenant' in k.lower():
                            uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', str(v), re.I)
                            if uuids:
                                tenant_token = uuids[0]
                                print(f"  [+] Found tenant-token inside key '{k}'!")
                                break
                            elif isinstance(v, str) and len(v) > 10:
                                tenant_token = v.strip('"\'')
                                print(f"  [+] Found tenant text in key '{k}'!")
                                break
                                
                    # Search logic 2: Look for ANY UUID that is NOT the main token
                    if not tenant_token:
                        for k, v in all_storage.items():
                            uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', str(v), re.I)
                            for uid in uuids:
                                if uid != token:
                                    tenant_token = uid
                                    print(f"  [+] Extracted hidden UUID from key '{k}', assuming it's tenant-token!")
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
    cleaned = re.sub(r'[^a-z0-9\s]', '', str(name).lower())
    return set(cleaned.split())

def match_names(name1, name2):
    set1 = clean_name(name1)
    set2 = clean_name(name2)
    if not set1 or not set2:
        return False
    return set1 == set2 or set1.issubset(set2) or set2.issubset(set1)

def parse_date(date_str):
    if pd.isna(date_str):
        return None
    try:
        return pd.to_datetime(date_str, dayfirst=True).date()
    except:
        return None

def fetch_crs_data(pid, token, tenant_token, search_name):
    print(f"  -> API Request with Name: '{search_name}'...")
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json;charset=UTF-8',
        'cookie': f'token={token}', 
        'origin': 'https://crs.fabhotels.com',
        'tenant-token': f'{tenant_token}',
        'token': f'{token}',
        'uri': 'admin/bookingsservice/admin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'
    }
    
    payload = {
        "bookingSearchRequestDto": {
            "pageNo": 1,
            "limit": 50, 
            "firstName": str(search_name),
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
        else:
            print(f"  -> API Error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"  -> Request failed: {e}")
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

    # NEW: Find ALL date-related columns
    for col in df.columns:
        col_lower = str(col).lower()
        if any(keyword in col_lower for keyword in ['date', 'c/in', 'c/out', 'check']):
            date_cols.append(col)
                
    return guest_col, date_cols

def process_ledger(excel_path, pid, token, tenant_token):
    print(f"\nReading Excel file: {excel_path}")
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    guest_col, date_cols = find_columns(df)
    
    if not guest_col or not date_cols:
        print("Could not automatically identify columns. Please ensure columns have 'name'/'guest' and 'date'/'checkout' in their headers.")
        return
        
    print(f"Identified Guest Column: '{guest_col}'")
    print(f"Identified Date Columns: {date_cols}")

    df['BID'] = "NOT FOUND"
    
    print("\nProcessing ledger rows...")
    for index, row in df.iterrows():
        ledger_name = row[guest_col]
        
        # Collect all dates available in this row
        ledger_dates = []
        for d_col in date_cols:
            d = parse_date(row[d_col])
            if d:
                ledger_dates.append(d)
        
        if pd.isna(ledger_name) or not ledger_dates:
            continue
            
        print(f"\n[{index+1}] Checking Guest: '{ledger_name}' with Dates: {ledger_dates}")
        found_bid = False
        
        name_parts = str(ledger_name).split()
        
        for part in name_parts:
            clean_part = re.sub(r'[^a-zA-Z0-9]', '', part)
            if len(clean_part) < 3: 
                continue
                
            crs_data = fetch_crs_data(pid, token, tenant_token, clean_part)
            print(f"  -> API returned {len(crs_data)} records for '{clean_part}'")
            
            for crs_record in crs_data:
                crs_first_name = crs_record.get('firstName', '')
                crs_last_name = crs_record.get('lastName', '')
                crs_full_name = f"{crs_first_name} {crs_last_name}".strip()
                
                crs_checkin_raw = crs_record.get('checkIn', '')
                crs_checkout_raw = crs_record.get('checkOut', '')
                
                crs_checkin_date = parse_date(crs_checkin_raw)
                crs_checkout_date = parse_date(crs_checkout_raw) 
                
                print(f"    - CRS Found: Name='{crs_full_name}', CI='{crs_checkin_date}', CO='{crs_checkout_date}', BID='{crs_record.get('bookingId')}'")
                
                name_matches = match_names(ledger_name, crs_full_name)
                
                # Check if ANY of the dates from Excel match
                date_matches = False
                if crs_checkin_date and crs_checkout_date:
                    for l_date in ledger_dates:
                        if crs_checkin_date <= l_date <= crs_checkout_date:
                            date_matches = True
                            break
                
                if name_matches:
                    print(f"      * Name Matches! Date match status: {date_matches}")
                if date_matches:
                    print(f"      * Date Matches! Name match status: {name_matches}")

                if name_matches and date_matches:
                    bid = crs_record.get('bookingId')
                    df.at[index, 'BID'] = bid
                    found_bid = True
                    print(f"  *** PERFECT MATCH FOUND! BID: {bid} ***")
                    break
            
            if found_bid:
                break
                
        if not found_bid:
             print(f"  --- No match found for '{ledger_name}' ---")

    output_path = excel_path.replace('.xlsx', '_processed.xlsx')
    try:
        df.to_excel(output_path, index=False)
        print(f"\nProcessing complete! Output saved to: {output_path}")
    except Exception as e:
        print(f"Error saving output file: {e}")


if __name__ == "__main__":
    print("--- CRs BID Extraction Automation ---")
    
    # Hide the main tkinter window
    root = tk.Tk()
    root.withdraw()
    
    # 1. Ask for PID
    pid = input("Enter Property ID (PID): ").strip()
    if not pid:
        print("PID is required!")
        sys.exit()

    # 2. Get Tokens automatically via Browser Login
    token, tenant_token = get_tokens_via_browser()
    
    if not token or not tenant_token:
        print("\nFailed to get one or both tokens automatically.")
        print("You can manually provide them below if you know them, otherwise the script will exit.")
        # Fallback to manual entry if automatic fails
        token = input("Enter 'token' manually (or press enter to skip): ").strip()
        tenant_token = input("Enter 'tenant-token' manually (or press enter to skip): ").strip()
        
    if not token or not tenant_token:
         print("Tokens are required. Exiting...")
         sys.exit()

    # 3. Select File
    print("\nPlease select your Excel ledger file from the dialog box...")
    excel_file = filedialog.askopenfilename(
        title="Select Hotel Ledger Excel File",
        filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
    )
    
    if not excel_file:
        print("No file selected. Exiting...")
        sys.exit()
        
    print(f"File selected: {excel_file}")
    
    # 4. Start processing
    process_ledger(excel_file, pid, token, tenant_token)

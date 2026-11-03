import pandas as pd
import requests
import json
import re
import time
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
MARVEL_URL = "https://crs.fabhotels.com/admin/hotel-settlement/payouts/bookings"
MARVEL_API_URL = "https://crs.fabhotels.com/admin/hotel-settlement/externalhotelsettlement/public/external/hotel/invoice/getall/data"
# ==========================================

def get_marvel_tokens_via_browser():
    print("\n[+] Opening Chrome browser for Marvel Login...")
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = None
    
    # 1. Try Selenium's built-in driver management (Selenium 4.6+)
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e1:
        print(f"[-] Selenium Manager attempt: {e1}")
        
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
            
            # 3. Try standard Chrome executable paths
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
        print("Please ensure Google Chrome is installed on your computer.")
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
    driver.get(MARVEL_URL)
    
    print("="*60)
    print("  PLEASE LOG IN TO MARVEL (ENTER OTP IF PROMPTED).")
    print("  Wait for the Payouts / Bookings page to load.")
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
            
            # Look for tenant-token
            try:
                # First check captured token in localStorage
                tt_captured = driver.execute_script("return localStorage.getItem('found-tenant-token');")
                if tt_captured:
                    tenant_token = tt_captured
                    
                if not tenant_token:
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
            except Exception:
                pass
                
            if token and tenant_token:
                print("\n[✔] Marvel tokens successfully extracted! Closing browser in 2 seconds...")
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


def fetch_marvel_batch(session, b_ids, token, tenant_token):
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'cookie': f'token={token}',
        'origin': 'https://crs.fabhotels.com',
        'referer': MARVEL_URL,
        'tenant-token': f'{tenant_token}',
        'token': f'{token}',
        'uri': '/externalhotelsettlement/public/external/hotel/invoice/getall/data',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36'
    }
    
    all_content = []
    current_page = 1
    total_pages = 1
    
    while current_page <= total_pages:
        payload = {
            "balanceAmount": None,
            "bankStatus": None,
            "bidTypeEnum": None,
            "bookingIds": ",".join(b_ids),
            "bookingSources": None,
            "checkinDate": None,
            "checkoutDate": None,
            "dueDays": None,
            "guestStatus": None,
            "page": current_page,
            "paymentStatus": None,
            "personalBooking": None,
            "propertyId": None,
            "searchPropertyIds": None,
            "size": max(len(b_ids), 50),
            "sourcingStatus": None
        }
        
        try:
            response = session.post(MARVEL_API_URL, headers=headers, json=payload, timeout=20)
            if response.status_code == 200:
                data = response.json().get('data', {})
                items = data.get('content', [])
                all_content.extend(items)
                total_pages = data.get('totalPages', 1)
                current_page += 1
            else:
                print(f"[-] API Error {response.status_code}: {response.text[:150]}")
                break
        except Exception as e:
            print(f"[-] Request failed: {e}")
            break
            
    return all_content


def extract_commission_fields(item):
    # Check for Hotel Commission
    hotel_comm = None
    for k in ['hotelCommission', 'travelPlusCommission', 'commission', 'tpCommission']:
        if k in item and item[k] is not None:
            hotel_comm = item[k]
            break
    if hotel_comm is None:
        tp_det = item.get('tpCommissionDetails') or {}
        hotel_comm = tp_det.get('amount', 0.0)

    # Check for GST on Hotel Commission
    gst_comm = None
    for k in ['gstOnHotelCommission', 'gstOnTravelPlusCommission', 'gstOnCommission', 'gstTravelPlusCommission']:
        if k in item and item[k] is not None:
            gst_comm = item[k]
            break
    if gst_comm is None:
        tp_det = item.get('tpCommissionDetails') or {}
        gst_comm = tp_det.get('taxAmount', 0.0)
        
    return float(hotel_comm or 0.0), float(gst_comm or 0.0)


def fetch_utr_details(session, bid, token, tenant_token):
    url = "https://crs.fabhotels.com/admin/hotel-settlement/externalhotelsettlement/public/hotel/payment/adjustment/getall"
    headers = {
        'accept': 'application/json, text/plain, */*',
        'cookie': f'token={token}',
        'origin': 'https://crs.fabhotels.com',
        'referer': MARVEL_URL,
        'tenant-token': f'{tenant_token}',
        'token': f'{token}',
        'uri': '/externalhotelsettlement/public/hotel/payment/adjustment/getall',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36'
    }
    params = {
        'bookingId': bid,
        'page': 1,
        'size': 100000
    }
    try:
        response = session.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json().get('data', {})
            return data.get('content', [])
    except Exception as e:
        print(f"[-] Failed to fetch UTR for {bid}: {e}")
    return []


def process_payouts(excel_path, token, tenant_token, include_commission=False):
    import openpyxl

    print(f"\nReading Excel file: {excel_path}")
    try:
        wb = openpyxl.load_workbook(excel_path)
    except Exception as e:
        print(f"Error loading Excel workbook: {e}")
        return

    # Find the target sheet that contains 'BID'
    target_sheet = None
    bid_col_idx = None
    header_row_idx = 1

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for r in range(1, min(10, ws.max_row + 1)):
            for c in range(1, ws.max_column + 1):
                val = ws.cell(row=r, column=c).value
                if val and str(val).strip().upper() == 'BID':
                    target_sheet = ws
                    bid_col_idx = c
                    header_row_idx = r
                    print(f"[+] Found 'BID' column in sheet '{sheet_name}' at column {openpyxl.utils.get_column_letter(c)}, row {r}")
                    break
            if target_sheet:
                break
        if target_sheet:
            break

    # Fallback to active sheet if not found by exact 'BID'
    if not target_sheet:
        ws = wb.active
        for r in range(1, min(10, ws.max_row + 1)):
            for c in range(1, ws.max_column + 1):
                val = ws.cell(row=r, column=c).value
                if val and ('bid' in str(val).lower() or 'booking id' in str(val).lower()):
                    target_sheet = ws
                    bid_col_idx = c
                    header_row_idx = r
                    print(f"[+] Found BID column in active sheet '{ws.title}' at column {openpyxl.utils.get_column_letter(c)}")
                    break
            if target_sheet:
                break

    if not target_sheet or not bid_col_idx:
        print("[-] Error: Could not find 'BID' column in any sheet.")
        return

    # Extract all valid BIDs
    unique_bids = set()
    for r in range(header_row_idx + 1, target_sheet.max_row + 1):
        val = target_sheet.cell(row=r, column=bid_col_idx).value
        if val is not None:
            b = str(val).strip().upper()
            if b and b != 'NOT FOUND' and b != 'NAN':
                unique_bids.add(b)

    total_bids = len(unique_bids)
    print(f"[+] Total unique BIDs to query from Marvel: {total_bids}")
    
    if total_bids == 0:
        print("[-] No valid BIDs found to process. Exiting...")
        return

    session = requests.Session()
    batch_size = 40
    bids_list = list(unique_bids)
    marvel_data_map = {}

    print("\nFetching data from Marvel API...")
    for i in range(0, total_bids, batch_size):
        batch = bids_list[i:i + batch_size]
        print(f" -> Querying batch {i//batch_size + 1} ({len(batch)} BIDs)...")
        
        items = fetch_marvel_batch(session, batch, token, tenant_token)
        for item in items:
            b_id = item.get('bookingId')
            if b_id:
                b_id_upper = str(b_id).strip().upper()
                paid_amt = float(item.get('paidAmount', 0.0) or 0.0)
                status = str(item.get('paymentStatus', '')).strip().lower()

                # Fetch UTRs if amount is paid or status is Processed/Paid
                utr_list = []
                if paid_amt > 0 or status in ['processed', 'paid']:
                    utr_records = fetch_utr_details(session, b_id, token, tenant_token)
                    for u in utr_records:
                        utr_list.append({
                            'utr': u.get('paidUTR', ''),
                            'date': u.get('paymentDate', ''),
                            'amount': u.get('paidAmount', 0.0)
                        })

                hotel_comm, gst_comm = extract_commission_fields(item)
                marvel_data_map[b_id_upper] = {
                    'TDS': item.get('tds', 0.0),
                    'TCS': item.get('tcs', 0.0),
                    'Payable': item.get('payableAmount', item.get('netPayableToProperty', 0.0)),
                    'HotelCommission': hotel_comm,
                    'GSTOnHotelCommission': gst_comm,
                    'UTRs': utr_list
                }
        time.sleep(0.5)

    print(f"\n[✔] Successfully retrieved Marvel data for {len(marvel_data_map)}/{total_bids} BIDs.")

    # Target columns directly adjacent to BID column
    col_tds = bid_col_idx + 1
    col_tcs = bid_col_idx + 2
    col_payable = bid_col_idx + 3

    if include_commission:
        col_hotel_comm = bid_col_idx + 4
        col_gst_hotel_comm = bid_col_idx + 5
        col_utr = bid_col_idx + 6
        col_pay_date = bid_col_idx + 7
        col_amount = bid_col_idx + 8
        headers_to_write = [
            (col_tds, 'TDS'),
            (col_tcs, 'TCS'),
            (col_payable, 'Payable'),
            (col_hotel_comm, 'Hotel Commission'),
            (col_gst_hotel_comm, 'GST on Hotel Commission'),
            (col_utr, 'UTR'),
            (col_pay_date, 'Payment Date'),
            (col_amount, 'Amount')
        ]
    else:
        col_hotel_comm = None
        col_gst_hotel_comm = None
        col_utr = bid_col_idx + 4
        col_pay_date = bid_col_idx + 5
        col_amount = bid_col_idx + 6
        headers_to_write = [
            (col_tds, 'TDS'),
            (col_tcs, 'TCS'),
            (col_payable, 'Payable'),
            (col_utr, 'UTR'),
            (col_pay_date, 'Payment Date'),
            (col_amount, 'Amount')
        ]

    # Write headers
    for c_idx, h_text in headers_to_write:
        target_sheet.cell(row=header_row_idx, column=c_idx, value=h_text)

    # Copy header styling if available
    ref_cell = target_sheet.cell(row=header_row_idx, column=bid_col_idx)
    for c_idx, _ in headers_to_write:
        c_cell = target_sheet.cell(row=header_row_idx, column=c_idx)
        if ref_cell.has_style:
            c_cell.font = openpyxl.styles.Font(name=ref_cell.font.name, size=ref_cell.font.size, bold=True)
            c_cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')

    # Populate rows from bottom to top so row insertion does not shift indices of unvisited rows
    start_row = header_row_idx + 1
    end_row = target_sheet.max_row

    for r in range(end_row, start_row - 1, -1):
        val = target_sheet.cell(row=r, column=bid_col_idx).value
        if val is None:
            continue
        b_clean = str(val).strip().upper()
        if b_clean not in marvel_data_map:
            continue

        info = marvel_data_map[b_clean]
        target_sheet.cell(row=r, column=col_tds, value=info['TDS'])
        target_sheet.cell(row=r, column=col_tcs, value=info['TCS'])
        target_sheet.cell(row=r, column=col_payable, value=info['Payable'])
        if include_commission:
            target_sheet.cell(row=r, column=col_hotel_comm, value=info['HotelCommission'])
            target_sheet.cell(row=r, column=col_gst_hotel_comm, value=info['GSTOnHotelCommission'])

        utrs = info.get('UTRs', [])
        if utrs:
            # First UTR goes on the current row
            target_sheet.cell(row=r, column=col_utr, value=utrs[0]['utr'])
            target_sheet.cell(row=r, column=col_pay_date, value=utrs[0]['date'])
            target_sheet.cell(row=r, column=col_amount, value=utrs[0]['amount'])

            # If there are additional UTRs, insert rows directly below (Option A)
            if len(utrs) > 1:
                num_extra = len(utrs) - 1
                target_sheet.insert_rows(r + 1, num_extra)
                for idx_extra, extra_utr in enumerate(utrs[1:]):
                    new_row = r + 1 + idx_extra
                    target_sheet.cell(row=new_row, column=col_utr, value=extra_utr['utr'])
                    target_sheet.cell(row=new_row, column=col_pay_date, value=extra_utr['date'])
                    target_sheet.cell(row=new_row, column=col_amount, value=extra_utr['amount'])

    base, _ = os.path.splitext(excel_path)
    output_path = f"{base}_with_payouts.xlsx"
    try:
        wb.save(output_path)
        print(f"\n======================================================")
        print(f"[✔] Complete! Output saved to: {output_path}")
        print(f"======================================================")
    except Exception as e:
        print(f"Error saving workbook: {e}")


if __name__ == "__main__":
    print("======================================================")
    print("        Marvel Payout & Tax Extractor (Step 2)        ")
    print("======================================================")
    
    root = tk.Tk()
    root.withdraw()

    print("\n" + "-"*60)
    comm_prompt = input("Do you want Hotel Commission and GST on Hotel Commission for this property? [Yes/No]: ").strip().lower()
    include_commission = comm_prompt in ['yes', 'y']
    if include_commission:
        print("[+] Hyperguest mode enabled: Hotel Commission and GST on Hotel Commission will be included.")
    else:
        print("[+] Normal mode: Standard TDS, TCS, and Payable will be included.")
    print("-" * 60)
    
    token, tenant_token = get_marvel_tokens_via_browser()
    
    if not token or not tenant_token:
        print("\nFailed to extract tokens automatically.")
        token = input("Enter 'token' manually (or press enter to skip): ").strip()
        tenant_token = input("Enter 'tenant-token' manually (or press enter to skip): ").strip()
        
    if not token or not tenant_token:
        print("Tokens are required. Exiting...")
        sys.exit()

    print("\nPlease select your processed Excel file (with BIDs)...")
    excel_file = filedialog.askopenfilename(
        title="Select Excel File with BIDs",
        filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
    )
    
    if not excel_file:
        print("No file selected. Exiting...")
        sys.exit()
        
    process_payouts(excel_file, token, tenant_token, include_commission=include_commission)

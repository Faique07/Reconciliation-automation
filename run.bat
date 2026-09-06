@echo off
echo Installing required libraries...
pip install pandas requests openpyxl selenium webdriver-manager

echo.
echo Running the automation script...
python crs_bid_extractor.py
pause

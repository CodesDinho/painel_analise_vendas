@echo off
cd /d "%~dp0\.."
python -m streamlit run main.py --server.port 8520 --server.headless true


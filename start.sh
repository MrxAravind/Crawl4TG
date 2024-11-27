python3 -m venv myenv  # Create a virtual environment (if not already created)
source myenv/bin/activate  # Activate the virtual environment
python3 -m ensurepip --upgrade  # Ensure pip is installed and upgrade it
pip install -r requirements.txt --break-system-packages
python3 -m playwright install chromium
python3 main.py

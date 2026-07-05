python -m venv .venv
# windows: .venv\Scripts\activate   |  *nix: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env #api keys here
python -m ctf_copilot.app

import json
import os
from pathlib import Path
from cryptography.fernet import Fernet

DATA_DIR = Path(os.environ.get("RETINA_DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
KEY_FILE = DATA_DIR / "encryption.key"


def _get_key() -> bytes:
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    os.chmod(KEY_FILE, 0o600)
    return key


def encrypt_credentials(credentials: dict) -> str:
    f = Fernet(_get_key())
    return f.encrypt(json.dumps(credentials).encode()).decode()


def decrypt_credentials(encrypted: str) -> dict:
    f = Fernet(_get_key())
    return json.loads(f.decrypt(encrypted.encode()).decode())

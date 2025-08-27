import requests


def get_public_ip() -> str:
    r = requests.get("https://checkip.amazonaws.com")
    r.raise_for_status()
    return r.text.strip()

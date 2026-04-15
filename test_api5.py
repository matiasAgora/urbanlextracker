import requests

try:
    resp = requests.post("http://127.0.0.1:8000/api/report/generate", json={})
    print(resp.status_code)
except Exception as e:
    print(e)

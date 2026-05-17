import json, urllib.parse, urllib.request

RAW = "fOroxLOTaQwVFKRFStMKoY3zhPTsmKV%2Bg4uIiCDQ53bwGXyYLl%2BHYstqRUOySbLKWDcuBXFFn7nN4x%2F8QcaClfjFmBvD6FKGhHTNGgfj2KDW3V%2FeIqeXtRelt6GA"
TOKEN = urllib.parse.unquote(RAW)
print("decoded token:", TOKEN)

def post(url, data, headers=None):
    h = {"Content-Type": "application/json"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

st, body = post("https://ctf.tjctf.org/api/v1/auth/login", {"teamToken": TOKEN})
print("LOGIN", st, body[:400])
jwt = None
try:
    jwt = json.loads(body)["data"]["authToken"]
    print("JWT:", jwt[:40], "...")
except Exception as e:
    print("no jwt", e)

if jwt:
    auth = {"Authorization": "Bearer " + jwt}
    for path in ["/api/challenge/vibecoded", "/api/challenges/vibecoded"]:
        st, b = get("https://instancer.tjctf.org" + path, auth)
        print("GET", path, st, b[:300])
    st, b = post("https://instancer.tjctf.org/api/challenge/vibecoded/create", {}, auth)
    print("CREATE", st, b[:600])

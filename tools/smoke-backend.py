"""Exercise only the local aion-foundation stack; preserves its volume and removes its test row."""

import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", "deploy/compose.yaml", "-f", "deploy/compose.local.yaml"]


def compose(*args: str) -> str:
    result = subprocess.run([*COMPOSE, *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(
            "Local foundation container operation failed; inspect sanitized service logs"
        )
    return result.stdout


def request(path: str, port: int = 18000) -> tuple[int, str, dict[str, str]]:
    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=8)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.code, response.read().decode(), dict(response.headers)


def wait_ready() -> None:
    for _ in range(20):
        try:
            if request("/api/v1/health/ready")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit("Local foundation did not become ready")


wait_ready()
assert json.loads(request("/api/v1/health/live")[1]) == {"status": "ok"}
assert request("/", 18080)[0] == 200
assert '<html lang="es">' in request("/es", 18080)[1]
code, body, headers = request("/api/v1/not-implemented", 18080)
assert code == 404 and json.loads(body) == {"error": {"code": "not_found"}}
assert headers.get("Cache-Control") == "no-store"
code, body, headers = request("/api", 18080)
assert code == 404 and json.loads(body)["error"]["code"] == "not_found"
assert headers.get("Content-Type", "").startswith("application/json")
try:
    compose("stop", "api")
    code, body, _ = request("/api/v1/health/ready", 18080)
    assert code == 503 and json.loads(body)["error"]["code"] == "unavailable"
    assert request("/", 18080)[0] == 200
finally:
    compose("start", "api")
    wait_ready()

# No input or secret is interpolated into a shell; only generated UUID/synthetic email below.
row_id = str(uuid.uuid4())
insert = (
    "from aion.config import Settings; from aion.database import make_engine; "
    "from sqlalchemy import text; e=make_engine(Settings()); "
    "c=e.connect(); t=c.begin(); "
    "c.execute(text('INSERT INTO users(id,email,verified_at) VALUES(:id,:email,now())'),"
    f"{{'id':'{row_id}','email':'foundation-{row_id}@example.test'}}); t.commit(); c.close()"
)
lookup = (
    "from aion.config import Settings; from aion.database import make_engine; "
    "from sqlalchemy import text; e=make_engine(Settings()); c=e.connect(); "
    f"assert c.execute(text('SELECT count(*) FROM users WHERE id=:id'),{{'id':'{row_id}'}})"
    ".scalar_one()==1; c.close()"
)
cleanup = (
    "from aion.config import Settings; from aion.database import make_engine; "
    "from sqlalchemy import text; e=make_engine(Settings()); c=e.connect(); t=c.begin(); "
    f"c.execute(text('DELETE FROM users WHERE id=:id'),{{'id':'{row_id}'}}); "
    "t.commit(); c.close()"
)
compose("exec", "-T", "api", "python", "-c", insert)
try:
    compose("stop", "postgres")
    assert request("/api/v1/health/live")[0] == 200
    assert request("/api/v1/health/ready")[0] == 503
    assert request("/", 18080)[0] == 200
finally:
    compose("start", "postgres")
    wait_ready()
try:
    compose("exec", "-T", "api", "python", "-c", lookup)
    compose("restart", "api", "worker")
    wait_ready()
    compose("exec", "-T", "api", "python", "-c", lookup)
    compose("exec", "-T", "worker", "python", "-m", "aion.worker", "--once")
finally:
    compose("exec", "-T", "api", "python", "-c", cleanup)
print(
    "PASS: proxy/JSON/cache headers, database outage/recovery, retained row and API/worker restart."
)

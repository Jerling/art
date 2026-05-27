"""Full pre-beta self-test with correct API inputs and env vars."""
import asyncio, json, sys, os

# Set required env vars
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "beta-test-secret-key-2026"
os.environ["SERVER_HOST"] = "127.0.0.1"
os.environ["SERVER_PORT"] = "8000"
os.environ["LLM_PROVIDER"] = "glm"
os.environ["GLM_API_KEY"] = "dummy-key-for-testing"
os.environ["REDIS_URL"] = ""

os.chdir("/home/jer/data/Code/art")
sys.path.insert(0, "/home/jer/data/Code/art")

from src.storage.database import engine
from src.models.role import Role

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Role.metadata.create_all)
    print("DB tables created OK\n")

asyncio.run(init_db())

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
results = []

def test(name, method, path, expected_status, **kwargs):
    r = getattr(client, method)(path, **kwargs)
    ok = r.status_code == expected_status
    status_str = "PASS" if ok else "FAIL"
    try:
        body = r.json()
    except Exception:
        body = r.text[:300]
    results.append({
        "name": name,
        "status": status_str,
        "expected": expected_status,
        "actual": r.status_code,
        "body": body
    })
    print(f"  [{status_str}] {name}: {r.status_code} (expected {expected_status})")
    if not ok:
        print(f"         Body: {str(body)[:200]}")
    return r

print("=" * 60)
print("PRE-BETA SELF-TEST — Art Agent MVP")
print("Branch: sprint3/mvp-launch | Date: 2026-05-27")
print("=" * 60)

# 1. Health checks
print("\n--- Health Checks ---")
test("Health endpoint", "get", "/health", 200)
test("Detailed health", "get", "/health/detailed", 200)
test("Metrics endpoint", "get", "/metrics", 200)

# 2. Role CRUD
print("\n--- Role CRUD ---")
r = test("Create role", "post", "/roles", 201,
         json={"name": "BetaTester", "description": "Beta test role"})
role_id = r.json().get("id", 0) if r.status_code == 201 else 0
print(f"  Role ID: {role_id}")

test("List roles", "get", "/roles", 200)
if role_id:
    test("Get single role", "get", f"/roles/{role_id}", 200)
    test("Delete role (204 is correct)", "delete", f"/roles/{role_id}", 204)
    test("Verify role deletion", "get", f"/roles/{role_id}", 404)

# 3. Task CRUD
print("\n--- Task CRUD ---")
r = test("Create task (uppercase priority)", "post", "/tasks", 201,
         json={"title": "Beta test task", "description": "Pre-beta validation", "priority": "MEDIUM"})
task_id = r.json().get("id", 0) if r.status_code == 201 else 0
print(f"  Task ID: {task_id}")

test("List tasks", "get", "/tasks", 200)
if task_id:
    test("Get task", "get", f"/tasks/{task_id}", 200)
    test("Update task status", "patch", f"/tasks/{task_id}/status", 200,
         json={"status": "IN_PROGRESS"})
    test("Update task", "put", f"/tasks/{task_id}", 200,
         json={"title": "Updated beta task", "status": "COMPLETED"})
    test("Delete task (204 is correct)", "delete", f"/tasks/{task_id}", 204)
    test("Verify task deletion", "get", f"/tasks/{task_id}", 404)

# 4. WeChat webhook (with required query params)
print("\n--- WeChat Webhook ---")
test("WeChat GET verification (with params)", "get", "/wechat/webhook", 200,
     params={"signature": "test", "timestamp": "1234567890", "nonce": "abc", "echostr": "test"})
test("WeChat POST (with signature)", "post", "/wechat/webhook", 200,
     params={"signature": "test", "timestamp": "1234567890", "nonce": "abc", "msg_signature": "test"},
     content=b"<xml><ToUserName>test</ToUserName><FromUserName>user1</FromUserName><MsgType>text</MsgType><Content>hello</Content></xml>",
     headers={"Content-Type": "application/xml"})

# 5. Messages & Admin
print("\n--- Messages & Admin ---")
test("List messages (with openid)", "get", "/messages", 200,
     params={"openid": "test_openid_1"})
test("List backups", "get", "/api/v1/admin/backup", 200)

# 6. Error handling
print("\n--- Error Handling ---")
test("Get non-existent task", "get", "/tasks/99999", 404)
test("Get non-existent role", "get", "/roles/99999", 404)
test("Create task without title", "post", "/tasks", 422)

# Summary
print("\n" + "=" * 60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
total = len(results)
print(f"RESULTS: {passed}/{total} passed, {failed} failed")

if failed > 0:
    print("\nFailed tests:")
    for r in results:
        if r["status"] == "FAIL":
            print(f"  - {r['name']}: expected {r['expected']}, got {r['actual']}")
            print(f"    {str(r['body'])[:150]}")
else:
    print("ALL TESTS PASSED")
print("=" * 60)

with open("/home/jer/.hermes/kanban/workspaces/t_8ca2a560/pre_beta_results.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("Results saved to pre_beta_results.json")

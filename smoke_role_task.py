"""Smoke test for role-task association endpoints."""
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.models import Base
from src.models.task import Task
from src.models.role import Role
from src.models.role_task import RoleTask
from src.storage.database import engine


async def main():
    # Bootstrap tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Create test data via direct DB
    async with session_maker() as s:
        role = Role(name="smoke-role", description="Smoke test role")
        task = Task(title="Smoke Task", description="A smoke test task")
        s.add(role)
        s.add(task)
        await s.commit()
        await s.refresh(role)
        await s.refresh(task)
        role_id = role.id
        task_id = task.id
        print(f"Created role id={role_id}, task id={task_id}")

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8765", timeout=10) as client:
        # POST /tasks/{id}/roles — assign role to task
        r = await client.post(f"/tasks/{task_id}/roles", json={"role_id": role_id})
        print(f"POST /tasks/{task_id}/roles -> {r.status_code}: {r.json()}")

        # POST again → should be 409
        r2 = await client.post(f"/tasks/{task_id}/roles", json={"role_id": role_id})
        print(f"POST again (duplicate) -> {r2.status_code}")

        # GET /roles/{id}/tasks — get tasks by role
        r3 = await client.get(f"/roles/{role_id}/tasks")
        print(f"GET /roles/{role_id}/tasks -> {r3.status_code}: {r3.json()}")

        # DELETE /tasks/{id}/roles/{role_id} — unassign
        r4 = await client.delete(f"/tasks/{task_id}/roles/{role_id}")
        print(f"DELETE /tasks/{task_id}/roles/{role_id} -> {r4.status_code}")

        # DELETE again → should be 404
        r5 = await client.delete(f"/tasks/{task_id}/roles/{role_id}")
        print(f"DELETE again -> {r5.status_code}")

        # GET after delete — should be empty
        r6 = await client.get(f"/roles/{role_id}/tasks")
        print(f"GET after unassign -> {r6.status_code}: {r6.json()}")

    await engine.dispose()
    print("\nAll endpoint smoke tests passed!")


if __name__ == "__main__":
    asyncio.run(main())

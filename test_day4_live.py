"""
Day 4 live test -- generates a real project via the Coding Agent (using
your real Groq key), writes it to disk, and hits its endpoints with
real HTTP requests via FastAPI's TestClient. No need to run uvicorn
separately or use a second terminal.

Run from the project root:
    python test_day4_live.py
"""

import os
import sys
import shutil

from app.agents.coding_agent import run_coding_agent
from app.rag.example_bank import EXAMPLE_BANK

OUT_DIR = os.path.join(os.path.dirname(__file__), "generated_projects", "inventory_app")


def main():
    spec = EXAMPLE_BANK[0]  # Inventory Management -- has the low-stock custom endpoint

    print("Calling Coding Agent (real Groq call + real embedding retrieval)...")
    files = run_coding_agent(spec)

    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    for f in files:
        path = os.path.join(OUT_DIR, f.path)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f.content)
    print(f"Wrote {len(files)} files to {OUT_DIR}")

    # Import the freshly generated main.py as a live module
    sys.path.insert(0, OUT_DIR)
    # Clear any stale cached modules from a previous run
    for mod in ["main", "models", "schemas", "services", "database"]:
        sys.modules.pop(mod, None)

    from fastapi.testclient import TestClient
    import main as generated_main
    import database
    import models

    client = TestClient(generated_main.app)

    print("\n--- Setting up test data ---")
    # The spec never defines POST /categories, so insert directly via DB
    db = database.SessionLocal()
    category = models.Category(name="Electronics")
    db.add(category)
    db.commit()
    db.refresh(category)
    category_id = category.id
    db.close()
    print(f"Inserted Category id={category_id} directly")

    print("\n--- Creating products ---")
    r = client.post("/products", json={
        "name": "Low Widget", "sku": "LOW-1", "stock_quantity": 2,
        "low_stock_threshold": 10, "category_id": category_id,
    })
    print("POST /products (low stock) ->", r.status_code)

    r = client.post("/products", json={
        "name": "High Widget", "sku": "HIGH-1", "stock_quantity": 100,
        "low_stock_threshold": 10, "category_id": category_id,
    })
    print("POST /products (well stocked) ->", r.status_code)

    print("\n--- Testing the LLM-generated custom endpoint ---")
    r = client.get("/products/low-stock")
    print("GET /products/low-stock ->", r.status_code)
    names = [p["name"] for p in r.json()]
    print("Products returned:", names)

    if r.status_code == 200 and names == ["Low Widget"]:
        print("\nPASS: low-stock endpoint correctly returned only the low-stock product")
    else:
        print("\nFAIL: expected only ['Low Widget'], check the generated function body")

    print("\n--- Sanity-checking standard CRUD still works ---")
    r = client.get("/products")
    print("GET /products -> ", r.status_code, f"({len(r.json())} total products)")


if __name__ == "__main__":
    main()

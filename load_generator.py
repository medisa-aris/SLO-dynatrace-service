"""
Playwright async load generator -- drives continuous traffic against the banking API.
5 workers, each randomly calling inquiry / withdrawal / transfer / health.

Usage:
    python load_generator.py
"""

import asyncio
import json
import random
import sys

from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8000"
ACCOUNT_IDS = [f"ACC{i:03d}" for i in range(1, 21)]
N_WORKERS = 5

ENDPOINT_WEIGHTS = {
    "inquiry": 40,
    "withdrawal": 30,
    "transfer": 25,
    "health": 5,
}

ENDPOINTS = list(ENDPOINT_WEIGHTS.keys())
WEIGHTS = list(ENDPOINT_WEIGHTS.values())


async def worker(worker_id: int):
    async with async_playwright() as p:
        ctx = await p.request.new_context(base_url=BASE_URL)
        request_count = 0
        error_count = 0

        while True:
            choice = random.choices(ENDPOINTS, weights=WEIGHTS, k=1)[0]
            try:
                if choice == "inquiry":
                    acc = random.choice(ACCOUNT_IDS)
                    resp = await ctx.get(f"/accounts/{acc}")
                    status = resp.status
                    print(f"[W{worker_id}] GET  /accounts/{acc:<6}              -> {status}")

                elif choice == "withdrawal":
                    acc = random.choice(ACCOUNT_IDS)
                    amount = round(random.uniform(10.0, 500.0), 2)
                    resp = await ctx.post(
                        f"/accounts/{acc}/withdrawal",
                        data=json.dumps({"amount": amount, "currency": "USD"}),
                        headers={"Content-Type": "application/json"},
                    )
                    status = resp.status
                    print(f"[W{worker_id}] POST /accounts/{acc}/withdrawal      -> {status}  amount={amount}")

                elif choice == "transfer":
                    from_acc, to_acc = random.sample(ACCOUNT_IDS, 2)
                    amount = round(random.uniform(10.0, 200.0), 2)
                    resp = await ctx.post(
                        "/transfers",
                        data=json.dumps(
                            {
                                "from_account_id": from_acc,
                                "to_account_id": to_acc,
                                "amount": amount,
                                "currency": "USD",
                            }
                        ),
                        headers={"Content-Type": "application/json"},
                    )
                    status = resp.status
                    print(f"[W{worker_id}] POST /transfers {from_acc}->{to_acc}           -> {status}  amount={amount}")

                elif choice == "health":
                    resp = await ctx.get("/health")
                    status = resp.status
                    print(f"[W{worker_id}] GET  /health                        -> {status}")

                request_count += 1
                if status >= 500:
                    error_count += 1

            except Exception as exc:
                error_count += 1
                print(f"[W{worker_id}] ERROR {choice}: {exc}", file=sys.stderr)

            await asyncio.sleep(random.uniform(0.5, 2.0))


async def main():
    print(f"Starting {N_WORKERS} load generator workers against {BASE_URL}")
    print("Press Ctrl+C to stop.\n")
    tasks = [asyncio.create_task(worker(i)) for i in range(1, N_WORKERS + 1)]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLoad generator stopped.")

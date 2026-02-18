#!/usr/bin/env python3
"""
benchmark.py — PHPyServer smoke test & benchmark
Usage: python benchmark.py [base_url] [requests_per_route]
"""

import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE   = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
N      = int(sys.argv[2]) if len(sys.argv) > 2 else 50
ROUTES = [
    ("/health",     "GET",  None),
    ("/api/ping",   "GET",  None),
    ("/api/users",  "GET",  None),
    ("/style.css",  "GET",  None),
    ("/blog",       "GET",  None),
    ("/api/echo",   "POST", b'{"hello":"world"}'),
]


def hit(args):
    url, method, body = args
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
            return (time.perf_counter() - t0) * 1000, r.status
    except urllib.error.HTTPError as e:
        return (time.perf_counter() - t0) * 1000, e.code
    except Exception as e:
        return (time.perf_counter() - t0) * 1000, 0


print(f"\nPHPyServer Benchmark — {BASE}  ({N} req × {len(ROUTES)} routes)\n")
print(f"{'Route':<22} {'Method':<6} {'Req':>4}  {'Avg':>7}  {'Min':>7}  {'Max':>7}  {'RPS':>7}  Status")
print("-" * 75)

for route, method, body in ROUTES:
    url  = BASE + route
    args = [(url, method, body)] * N
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(hit, args))
    elapsed  = time.perf_counter() - t_start
    times    = [r[0] for r in results]
    statuses = [r[1] for r in results]
    ok       = sum(1 for s in statuses if 200 <= s < 400)
    avg      = sum(times) / len(times)
    rps      = N / elapsed
    print(f"{route:<22} {method:<6} {N:>4}  {avg:>6.1f}ms {min(times):>6.1f}ms {max(times):>6.1f}ms {rps:>6.0f}/s  {ok}/{N} ok")

print()

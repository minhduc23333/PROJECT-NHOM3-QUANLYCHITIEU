"""Đo thời gian phản hồi API trên SERVER THẬT (MySQL thật) - T05E186: yêu cầu mỗi API < 2 giây.

Cách dùng (server đang chạy ở cổng 8000, database đã có dữ liệu, vd chạy `python -m scripts.seed`):
    python -m scripts.check_api_latency
    python -m scripts.check_api_latency --base http://127.0.0.1:8000 --email an@demo.vn --password 123456 --runs 5
Thoát với mã 1 nếu có API chậm hơn --limit giây (mặc định 2.0).
"""
import argparse
import statistics
import sys
import time

import httpx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--email", default="an@demo.vn")
    ap.add_argument("--password", default="123456")
    ap.add_argument("--runs", type=int, default=5, help="số lần gọi mỗi API")
    ap.add_argument("--limit", type=float, default=2.0, help="ngưỡng giây")
    a = ap.parse_args()

    with httpx.Client(base_url=a.base, timeout=30.0) as c:
        t0 = time.perf_counter()
        r = c.post("/api/auth/login", json={"email": a.email, "password": a.password})
        login_dt = time.perf_counter() - t0
        if r.status_code != 200:
            print(f"Đăng nhập thất bại ({r.status_code}): {r.text[:200]}")
            return 2
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        paths = ["/api/auth/me", "/api/dashboard/summary", "/api/groups"]
        groups = c.get("/api/groups", headers=h).json()
        if groups:
            gid = groups[0]["id"]
            paths += [f"/api/groups/{gid}", f"/api/groups/{gid}/receipts", f"/api/groups/{gid}/debts"]
            receipts = c.get(f"/api/groups/{gid}/receipts", headers=h).json()
            if receipts:
                rid = receipts[0]["id"]
                paths += [f"/api/receipts/{rid}", f"/api/receipts/{rid}/selections", f"/api/receipts/{rid}/debts"]
        paths.append("/api/receipts/category-suggestion?merchant_name=Highlands")

        rows = [("POST /api/auth/login", [login_dt])]
        for p in paths:
            times = []
            for _ in range(a.runs):
                t0 = time.perf_counter()
                res = c.get(p, headers=h)
                times.append(time.perf_counter() - t0)
                if res.status_code != 200:
                    print(f"CẢNH BÁO: GET {p} trả {res.status_code}")
                    break
            rows.append((f"GET {p}", times))

    print(f"{'API':58} {'nhanh nhất':>10} {'trung bình':>10} {'chậm nhất':>10}")
    slow = 0
    for name, ts in rows:
        worst = max(ts)
        flag = "  <-- CHẬM" if worst >= a.limit else ""
        slow += worst >= a.limit
        print(f"{name[:58]:58} {min(ts):9.3f}s {statistics.mean(ts):9.3f}s {worst:9.3f}s{flag}")
    print(f"\nNgưỡng {a.limit:.1f}s: " + ("TẤT CẢ ĐẠT" if not slow else f"{slow} API CHẬM, cần tối ưu"))
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())

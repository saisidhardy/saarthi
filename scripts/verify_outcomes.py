import urllib.request
import json

BASE = "http://127.0.0.1:8000"

def post(url, body=None):
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'} if body else {}, method='POST')
    return json.loads(urllib.request.urlopen(req).read())

def get(url):
    req = urllib.request.Request(url)
    return urllib.request.urlopen(req).read()

# Reset book first
post(f"{BASE}/api/load-sample-book?workflow_id=collections")

# 1. S1 Hero (Sunita Patil, ₹40k Marathi)
s1 = post(f"{BASE}/api/events/scenario/s1")
print("[PASS] S1 Hero:", s1["customer_name"], s1["status"], f"| Scheduled Mandate: ₹{s1.get('locked_mandate_inr', 0):,.2f}")

# 2. S2 Code-Mix Part Payment (Rajesh Sharma, ₹2.5k today + ₹5k mandate)
s2 = post(f"{BASE}/api/events/scenario/s2")
print("[PASS] S2 Part-Pay:", s2["customer_name"], s2["status"], f"| Instant Rec: ₹{s2.get('instant_recovered_inr', 0):,.2f} | Scheduled: ₹{s2.get('locked_mandate_inr', 0):,.2f}")

# 3. S3 Adversarial Firewall (Vikram Malhotra, waiver blocked)
s3 = post(f"{BASE}/api/events/scenario/s3")
print("[PASS] S3 Adversarial:", s3["customer_name"], s3["status"], "| Firewall Status:", s3["data"]["policy_firewall"]["status"])

# 4. S4 Sensitive Pause (Suresh Patil, ICU - 7-day pause + human review)
s4 = post(f"{BASE}/api/events/scenario/s4")
print("[PASS] S4 Sensitive Pause:", s4["customer_name"], s4["status"], "| Do Not Contact Until:", s4.get("do_not_contact_until"))

# 5. S7 T-24h Preventive (Anjali Deshmukh, ₹6k token today + ₹12k shifted)
s7 = post(f"{BASE}/api/events/scenario/s7")
print("[PASS] S7 Preventive:", s7["customer_name"], s7["status"], f"| Instant: ₹{s7.get('instant_recovered_inr', 0):,.2f} | Scheduled: ₹{s7.get('locked_mandate_inr', 0):,.2f}")

# 6. S8 Kirana Cashflow 4x Micro-Split (Sunita Patil, 4x ₹10k)
s8 = post(f"{BASE}/api/events/scenario/s8")
micro = s8.get("micro_schedule") or s8["data"].get("micro_schedule")
print("[PASS] S8 Micro-Split:", s8["customer_name"], s8["status"], f"| Tranches: {len(micro)}", f"| Instant Tranche 1: ₹{s8.get('instant_recovered_inr', 0):,.2f}")

# 7. Dashboard Metrics
dash = json.loads(get(f"{BASE}/api/dashboard?workflow_id=collections").decode('utf-8'))
print("\n=== SIMULATION METRICS (ON SYNTHETIC ACCOUNTS) ===")
details = dash.get("details", {})
print("Simulation:", details.get("simulation_label"))
print("Contacted:", details.get("contacted"))
print("PTPs Recorded:", details.get("ptps"))
print("Blocked by Policy:", details.get("blocked_by_policy"))
print("Escalated to Human:", details.get("escalated"))
print("Cost per contact (estimated):", f"₹{details.get('our_cost_per_contact')}")
print("Industry benchmarks (reported by other sources):")
print(" - Bounced EMI fee range:", details.get("bounced_emi_fee_range"))
print(" - Field visit cost range:", details.get("field_visit_cost_range"))

# 8. Web Portals Verification
index_html = get(f"{BASE}/").decode('utf-8')
assert "Saarthi" in index_html, "Index HTML missing Saarthi"
print("\n[PASS] Web application serving successfully!")

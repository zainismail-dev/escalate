"""Fail on ZAP baseline alerts of Medium risk or higher; print every alert.

    python .zap/gate.py zap-report.json

Accepted lower-risk alerts are listed with a reason in docs/SECURITY_AUDIT.md (section ZAP).
"""

import json
import sys

FAIL_AT = 2  # riskcode: 0 info, 1 low, 2 medium, 3 high


def main(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        report = json.load(f)
    failed = 0
    for site in report.get("site", []):
        for alert in site.get("alerts", []):
            risk = int(alert["riskcode"])
            line = f"{site['@name']}: [{alert['riskdesc']}] {alert['pluginid']} {alert['alert']}"
            print(line, f"({alert['count']} instance(s))")
            if risk >= FAIL_AT:
                failed += 1
                for inst in alert.get("instances", [])[:5]:
                    print("    ", inst.get("method", ""), inst.get("uri", ""))
    print(f"{failed} alert(s) at Medium or above")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

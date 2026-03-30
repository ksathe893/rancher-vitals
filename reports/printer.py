"""
reports/printer.py

Formats and prints verdicts.
This is the only file that knows about output format.
Swap this out later for JSON, HTML, Slack — without touching anything else.
"""

from interpreters.cpu import OK, WARN, CRITICAL

ICONS = { OK: "✅ ", WARN: "⚠️ ", CRITICAL: "🔴" }
SEP   = "─" * 52


def _severity_order(v):
    return {CRITICAL: 0, WARN: 1, OK: 2}.get(v.status, 3)


def print_report(verdicts, raw_data):
    cpus = raw_data["cpu_count"]

    print()
    print("━" * 52)
    print(f"  RANCHER VITALS  —  {cpus} CPUs")
    print("━" * 52)

    # Critical + warn first, then ok
    for v in sorted(verdicts, key=_severity_order):
        icon = ICONS.get(v.status, "  ")
        print()
        print(f"{icon}  {v.metric.upper()}")
        print(f"    Value:   {v.value}")
        print(f"    Status:  {v.summary}")
        print(f"    Why:     {v.why}")
        if v.action:
            print(f"    Action:  {v.action}")
        print(SEP)

    # D-state process detail
    if raw_data.get("d_state_procs"):
        print()
        print("  D-STATE PROCESSES  (blocked on I/O — cannot be killed)")
        print(SEP)
        for name in raw_data["d_state_procs"]:
            print(f"    {name}")

    # Overall
    statuses = [v.status for v in verdicts]
    print()
    if CRITICAL in statuses:
        print("  OVERALL: 🔴 NODE NEEDS ATTENTION")
    elif WARN in statuses:
        print("  OVERALL: ⚠️  NODE UNDER PRESSURE — monitor closely")
    else:
        print("  OVERALL: ✅  NODE IS HEALTHY")

    print("━" * 52)
    print()

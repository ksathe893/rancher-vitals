"""
reports/printer.py

Formats and prints verdicts in an elaborated, educational way.
Teaches the engineer what each metric means and how it was assessed.
"""

from interpreters.cpu import OK, WARN, CRITICAL

ICONS = {OK: "OK  ", WARN: "WARN", CRITICAL: "CRIT"}
SEP   = "=" * 64
THIN  = "-" * 64


def _severity_order(v):
    return {CRITICAL: 0, WARN: 1, OK: 2}.get(v.status, 3)


def _print_header(raw_data):
    cpus    = raw_data["cpu_count"]
    l1      = raw_data["load1"]
    l5      = raw_data["load5"]
    l15     = raw_data["load15"]
    running = raw_data["procs_running"]

    print()
    print(SEP)
    print("  RANCHER VITALS  --  CPU & LOAD ANALYSIS")
    print(SEP)
    print()
    print("  Node overview:")
    print("    CPU cores    : {}".format(cpus))
    print("    Load average : {} (1min)   {} (5min)   {} (15min)".format(l1, l5, l15))
    print("    Running now  : {} process(es) actively on a CPU".format(running))
    print()
    print("  How to read load average:")
    print("    Load average = how many processes are running OR waiting for CPU.")
    print("    On its own the number means nothing -- it must be compared")
    print("    to your CPU count. A load of 4.0 on a 4-core node = 100%")
    print("    utilised. The same load on a 32-core node = totally fine.")
    print()
    print("  Trend guide:")
    print("    1min > 15min = load is INCREASING (getting worse)")
    print("    1min < 15min = load is DECREASING (recovering)")
    print("    1min ~ 15min = load is STABLE")
    print(THIN)


def _print_verdict(v, index):
    icon = ICONS.get(v.status, "    ")
    sym  = "!" if v.status == CRITICAL else ("~" if v.status == WARN else " ")

    print()
    print("  [{}] {}  {}".format(sym, icon, v.metric.upper()))
    print()
    print("  Measured value:")
    print("    {}".format(v.value))
    print()
    print("  Assessment:")
    print("    {}".format(v.summary))
    print()
    print("  Why this matters for Kubernetes:")

    # Word-wrap the why text at 58 chars
    words = v.why.split()
    line  = "    "
    for word in words:
        if len(line) + len(word) + 1 > 62:
            print(line)
            line = "    " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)

    if v.action:
        print()
        print("  What to do next:")
        words = v.action.split()
        line  = "    "
        for word in words:
            if len(line) + len(word) + 1 > 62:
                print(line)
                line = "    " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)

    print()
    print(THIN)


def _print_processes(raw_data):
    d_procs = raw_data.get("d_state_procs", [])
    zombies = raw_data.get("zombie_procs",  [])

    if not d_procs and not zombies:
        return

    print()
    print("  PROCESS STATE DETAIL")
    print()

    if d_procs:
        print("  D-state processes  (uninterruptible sleep -- blocked on I/O):")
        print("  These processes are WAITING for disk or network I/O to complete.")
        print("  They cannot be killed. Their presence confirms a real I/O bottleneck.")
        print()
        for name in d_procs:
            print("    [D]  {}".format(name))
        print()

    if zombies:
        print("  Zombie processes  (dead but not yet cleaned up by parent):")
        print("  These consume PIDs but no CPU or memory. A few is normal.")
        print("  Many zombies = container runtime or kubelet may have a bug.")
        print()
        for name in zombies:
            print("    [Z]  {}".format(name))
        print()

    print(THIN)


def _print_overall(verdicts):
    statuses = [v.status for v in verdicts]
    print()

    if CRITICAL in statuses:
        critical_items = [v.metric for v in verdicts if v.status == CRITICAL]
        print("  OVERALL VERDICT:  !! CRITICAL -- NODE NEEDS IMMEDIATE ATTENTION")
        print()
        print("  Critical issues found:")
        for item in critical_items:
            print("    - {}".format(item))
        print()
        print("  Start with the CRITICAL items above. Each one has a suggested")
        print("  next step. Address the highest-impact issue first.")

    elif WARN in statuses:
        warn_items = [v.metric for v in verdicts if v.status == WARN]
        print("  OVERALL VERDICT:  ~~ WARNING -- NODE IS UNDER PRESSURE")
        print()
        print("  Items to watch:")
        for item in warn_items:
            print("    - {}".format(item))
        print()
        print("  No immediate crisis but these need attention. Monitor the")
        print("  trend -- if they worsen, escalate to critical investigation.")

    else:
        print("  OVERALL VERDICT:  OK -- NODE IS HEALTHY")
        print()
        print("  All CPU and load metrics are within normal range.")
        print("  No action required at this time.")

    print()
    print(SEP)
    print()


def print_report(verdicts, raw_data):
    _print_header(raw_data)

    # Critical and warn first, then ok
    for v in sorted(verdicts, key=_severity_order):
        _print_verdict(v, 0)

    _print_processes(raw_data)
    _print_overall(verdicts)

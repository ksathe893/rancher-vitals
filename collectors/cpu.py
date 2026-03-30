"""
collectors/cpu.py

ONLY collects raw data. No interpretation, no logic.
Returns a plain dict of numbers.
"""

import time


def _read_proc_stat():
    """Read /proc/stat and return parsed CPU lines."""
    with open("/proc/stat") as f:
        lines = f.readlines()

    cpus = {}
    for line in lines:
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        name = parts[0]  # "cpu", "cpu0", "cpu1" ...
        fields = list(map(int, parts[1:]))
        cpus[name] = {
            "user":    fields[0],
            "nice":    fields[1],
            "system":  fields[2],
            "idle":    fields[3],
            "iowait":  fields[4] if len(fields) > 4 else 0,
            "irq":     fields[5] if len(fields) > 5 else 0,
            "softirq": fields[6] if len(fields) > 6 else 0,
            "steal":   fields[7] if len(fields) > 7 else 0,
        }

    # context switches and running processes also in /proc/stat
    ctxt = 0
    procs_running = 0
    for line in lines:
        if line.startswith("ctxt"):
            ctxt = int(line.split()[1])
        if line.startswith("procs_running"):
            procs_running = int(line.split()[1])

    return cpus, ctxt, procs_running


def _calc_delta(snap1, snap2):
    """Calculate CPU % from two /proc/stat snapshots."""
    result = {}
    for cpu_name in snap1:
        if cpu_name not in snap2:
            continue
        s1 = snap1[cpu_name]
        s2 = snap2[cpu_name]

        # Total ticks elapsed
        total = sum(s2[k] - s1[k] for k in s1)
        if total == 0:
            continue

        idle = (s2["idle"] - s1["idle"]) + (s2["iowait"] - s1["iowait"])
        result[cpu_name] = {
            "user":    round((s2["user"]    - s1["user"])    / total * 100, 1),
            "system":  round((s2["system"]  - s1["system"])  / total * 100, 1),
            "idle":    round((s2["idle"]    - s1["idle"])    / total * 100, 1),
            "iowait":  round((s2["iowait"]  - s1["iowait"])  / total * 100, 1),
            "softirq": round((s2["softirq"] - s1["softirq"]) / total * 100, 1),
            "steal":   round((s2["steal"]   - s1["steal"])   / total * 100, 1),
            "irq":     round((s2["irq"]     - s1["irq"])     / total * 100, 1),
        }
    return result


def _get_cpu_count():
    count = 0
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("processor"):
                count += 1
    return count


def _get_load_average():
    with open("/proc/loadavg") as f:
        parts = f.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def _get_process_states():
    """Count D-state and zombie processes from /proc."""
    import os
    d_state = []
    zombies = []

    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/status") as f:
                content = f.read()
            name = ""
            state = ""
            for line in content.splitlines():
                if line.startswith("Name:"):
                    name = line.split()[1]
                if line.startswith("State:"):
                    state = line.split()[1]
            if state == "D":
                d_state.append(name)
            elif state == "Z":
                zombies.append(name)
        except Exception:
            continue

    return d_state, zombies


def collect_cpu():
    """
    Main collector. Returns raw dict — no interpretation.
    Takes 1 second (needs two /proc/stat reads to calculate rates).
    """
    cpu_count = _get_cpu_count()
    load1, load5, load15 = _get_load_average()

    # Two snapshots 1 second apart for accurate CPU %
    snap1, ctxt1, procs_running = _read_proc_stat()
    time.sleep(1)
    snap2, ctxt2, _ = _read_proc_stat()

    cpu_pcts = _calc_delta(snap1, snap2)
    context_switches_per_sec = ctxt2 - ctxt1

    d_state_procs, zombie_procs = _get_process_states()

    return {
        "cpu_count":               cpu_count,
        "load1":                   load1,
        "load5":                   load5,
        "load15":                  load15,
        "cpu_pcts":                cpu_pcts,        # "cpu", "cpu0", "cpu1" ...
        "context_switches_per_sec": context_switches_per_sec,
        "procs_running":           procs_running,
        "d_state_procs":           d_state_procs,   # list of process names
        "zombie_procs":            zombie_procs,     # list of process names
    }

# rancher-vitals

> Live node performance interpreter for Rancher/K8s support engineers.

---

## The Problem

When a customer node is struggling, you SSH in and run commands like `top`, `vmstat`, `iostat`. You get walls of numbers. Making sense of them — *is this iowait bad? is this load average critical on this machine? which pod is causing it?* — takes experience and time. During a P1 at 2am, that's exactly what you don't have.

## What This Does

`rancher-vitals` runs on any Linux node, collects performance data, and tells you **in plain English** what is wrong, why it matters for Kubernetes, and what to do next.

```
python3 vitals.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 RANCHER VITALS — node-2 — 2 CPUs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴  LOAD AVERAGE
    Value:   5.83 / 3.21 / 1.12  (1min / 5min / 15min)
    Status:  Node is overloaded — 2.9x CPU count, increasing
    Why:     More work queued than CPUs can handle.
             Kubelet may miss heartbeats → NotReady risk.
    Action:  Check top processes below.

⚠️   CPU — iowait 24%
    Value:   us=12% sy=4% id=59% wa=24% si=1%
    Status:  Disk is the bottleneck, not CPU
    Why:     CPUs are idle but waiting for disk I/O.
             etcd write latency will be elevated.
    Action:  Run iostat — disk module coming next.

✅  CONTEXT SWITCHES
    Value:   4,821 switches/sec
    Status:  Normal range for this node

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TOP PROCESSES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 containerd     38.2%  [D-state — blocked on I/O]
 kubelet        21.0%
 etcd            8.1%  [D-state — blocked on I/O]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 OVERALL: 🔴 NODE NEEDS ATTENTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## How It's Different

| What exists today | rancher-vitals |
|---|---|
| `top`, `vmstat`, `iostat` — raw numbers | Plain-English verdicts |
| Prometheus/Grafana — needs pre-installation | Zero dependencies, works anywhere |
| Generic Linux tools — no K8s context | Knows about etcd, kubelet, containerd |

---

## Design Principles

**1. No dependencies**
Everything reads from `/proc` and `/sys` — always available on any Linux node.
Commands like `iostat`, `mpstat` are used as enrichment if available, never required.

**2. Modular**
Each check is its own collector + interpreter. Easy to add, easy to test, easy to understand.

**3. Layered**
- Layer 1 — OS basics: CPU, memory, disk, network
- Layer 2 — K8s depth: conntrack, inotify, etcd disk, OOMKill history

**4. Plain English**
Every metric has: value → status → why it matters → what to do next.
A junior engineer should understand the output without googling.

---

## Project Structure

```
rancher-vitals/
│
├── vitals.py                   ← entry point, run this
│
├── collectors/                 ← RAW data collection, no logic
│   ├── cpu.py                  ← reads /proc/stat, /proc/cpuinfo
│   ├── memory.py               ← reads /proc/meminfo        [coming]
│   ├── disk.py                 ← reads /proc/diskstats, df  [coming]
│   └── network.py              ← reads /proc/net/dev, ss    [coming]
│
├── interpreters/               ← LOGIC — turns numbers into verdicts
│   ├── cpu.py                  ← what does this iowait mean?
│   ├── memory.py               ← [coming]
│   ├── disk.py                 ← [coming]
│   └── network.py              ← [coming]
│
└── reports/
    └── printer.py              ← formats and prints the report
```

**Collectors** just gather data. No logic, no opinions.
**Interpreters** apply the knowledge — thresholds, K8s context, verdicts.
**Reports** format and print. Swap this out later for JSON output, HTML, Slack message.

---

## Current Status

| Module | Collector | Interpreter | Status |
|---|---|---|---|
| Load average | ✅ | ✅ | Done |
| CPU breakdown (iowait, steal, softirq) | 🔨 | 🔨 | In progress |
| Per-core breakdown | 📋 | 📋 | Planned |
| Process-level (D-state, zombie) | 📋 | 📋 | Planned |
| Context switches | 📋 | 📋 | Planned |
| Memory | 📋 | 📋 | Planned |
| Disk I/O | 📋 | 📋 | Planned |
| Network | 📋 | 📋 | Planned |
| K8s depth (conntrack, inotify, etcd) | 📋 | 📋 | Planned |

---

## Roadmap

**Phase 1 — CPU module** ← we are here
Full CPU picture: load, iowait, steal, per-core, D-state processes, context switches.

**Phase 2 — Memory module**
Real available memory, swap, OOMKill history, slab cache.

**Phase 3 — Disk module**
iostat interpretation, etcd disk path check, partition fullness, inode exhaustion.

**Phase 4 — Network module**
conntrack table, socket states, interface errors.

**Phase 5 — K8s depth**
kubelet/containerd service health, inotify limits, PID limits, etcd-specific checks.

**Phase 6 — Multi-node**
Run against multiple nodes via SSH, compare, find the outlier.

---

## Usage

```bash
# Run on the node you're SSHed into
python3 vitals.py

# No pip install needed. No dependencies.
# Works on Ubuntu, RHEL, SLES, Flatcar — anything with /proc
```

---

## Contributing

Each module is independent. To add a new check:
1. Add a collector in `collectors/` — just reads raw data, returns a dict
2. Add an interpreter in `interpreters/` — takes the dict, returns a Verdict
3. Register it in `vitals.py`

That's it.

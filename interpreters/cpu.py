"""
interpreters/cpu.py
Compatible with Python 3.6+
"""

OK       = "ok"
WARN     = "warn"
CRITICAL = "critical"


class Verdict:
    def __init__(self, metric, value, status, summary, why, action):
        self.metric  = metric
        self.value   = value
        self.status  = status
        self.summary = summary
        self.why     = why
        self.action  = action


def _verdict_load(data):
    l1, l5, l15 = data["load1"], data["load5"], data["load15"]
    cpus  = data["cpu_count"]
    ratio = l1 / cpus

    if l1 > l15 * 1.2:
        trend = "and increasing"
    elif l1 < l15 * 0.8:
        trend = "and recovering"
    else:
        trend = "stable"

    value = "{} / {} / {}  (1min/5min/15min)  |  {} CPUs".format(l1, l5, l15, cpus)

    if ratio < 0.7:
        return Verdict(metric="Load average", value=value, status=OK,
            summary="Healthy -- {:.1f}x CPU count, {}".format(ratio, trend),
            why="CPUs have headroom. No pressure.", action="")
    elif ratio < 1.0:
        return Verdict(metric="Load average", value=value, status=WARN,
            summary="Elevated -- {:.1f}x CPU count, {}".format(ratio, trend),
            why="CPUs are busy. Not yet overloaded but watch the trend.",
            action="Monitor. If load_1 keeps rising, check top processes.")
    else:
        return Verdict(metric="Load average", value=value, status=CRITICAL,
            summary="Overloaded -- {:.1f}x CPU count, {}".format(ratio, trend),
            why="More work queued than {} CPUs can handle. Kubelet may miss heartbeats -> NotReady risk.".format(cpus),
            action="Check D-state processes and top CPU consumers below.")


def _verdict_iowait(data):
    cpu = data["cpu_pcts"].get("cpu", {})
    wa  = cpu.get("iowait",  0)
    us  = cpu.get("user",    0)
    sy  = cpu.get("system",  0)
    id_ = cpu.get("idle",    0)
    si  = cpu.get("softirq", 0)
    st  = cpu.get("steal",   0)

    value = "user={}%  sys={}%  idle={}%  iowait={}%  softirq={}%  steal={}%".format(us, sy, id_, wa, si, st)

    if wa > 20:
        return Verdict(metric="CPU iowait", value=value, status=CRITICAL,
            summary="Disk bottleneck -- iowait {}%".format(wa),
            why="CPUs spending {}% of time waiting for disk. etcd write latency will be elevated.".format(wa),
            action="Run iostat -x 1 3 to identify which disk.")
    elif wa > 10:
        return Verdict(metric="CPU iowait", value=value, status=WARN,
            summary="Moderate disk pressure -- iowait {}%".format(wa),
            why="Some I/O wait. Healthy is under 5%. etcd may see occasional write delays.",
            action="Watch if iowait rises. Run iostat to identify disk.")
    elif st > 5:
        return Verdict(metric="CPU steal", value=value, status=CRITICAL,
            summary="Hypervisor stealing CPU -- steal {}%".format(st),
            why="{}% of CPU given to another VM. Noisy neighbour. Tuning won't help.".format(st),
            action="Report to cloud provider. Consider moving to different host.")
    elif si > 5:
        return Verdict(metric="CPU softirq", value=value, status=WARN,
            summary="High network interrupt load -- softirq {}%".format(si),
            why="Kernel handling heavy network interrupts. Possible NIC saturation.",
            action="Check network with ss -s and ip -s link.")
    else:
        return Verdict(metric="CPU breakdown", value=value, status=OK,
            summary="Healthy -- {}% idle, iowait {}%".format(id_, wa),
            why="No CPU pressure. iowait, softirq and steal all within normal range.",
            action="")


def _verdict_per_core(data):
    pcts  = data["cpu_pcts"]
    cores = {k: v for k, v in pcts.items() if k != "cpu"}
    if not cores:
        return None

    busiest    = max(cores.items(), key=lambda x: x[1].get("user", 0) + x[1].get("system", 0))
    core_name  = busiest[0]
    core_usage = busiest[1].get("user", 0) + busiest[1].get("system", 0)
    overall    = pcts.get("cpu", {})
    overall_usage = overall.get("user", 0) + overall.get("system", 0)

    value = "busiest core: {} at {}%  |  overall avg: {}%".format(core_name, core_usage, overall_usage)

    if core_usage > 90 and overall_usage < 60:
        return Verdict(metric="Per-core CPU", value=value, status=WARN,
            summary="Single-core saturation on {} ({}%)".format(core_name, core_usage),
            why="Overall CPU fine ({}%) but {} is saturated. etcd writes are single-threaded -- invisible in summary.".format(overall_usage, core_name),
            action="Check with ps -eo pid,psr,comm.")
    elif core_usage > 95:
        return Verdict(metric="Per-core CPU", value=value, status=CRITICAL,
            summary="{} fully saturated at {}%".format(core_name, core_usage),
            why="Core maxed out. etcd or kubelet on this core will show latency spikes.",
            action="Check affinity with ps -eo pid,psr,comm.")
    else:
        return Verdict(metric="Per-core CPU", value=value, status=OK,
            summary="Balanced -- busiest core at {}%".format(core_usage),
            why="CPU load spread evenly across cores.", action="")


def _verdict_context_switches(data):
    cs       = data["context_switches_per_sec"]
    cpus     = data["cpu_count"]
    per_core = cs // cpus if cpus else cs

    value = "{:,} switches/sec  ({:,} per core)".format(cs, per_core)

    if per_core > 100000:
        return Verdict(metric="Context switches", value=value, status=WARN,
            summary="High context switch rate -- {:,}/sec per core".format(per_core),
            why="Kernel rapidly switching between processes. Dense K8s pods with sidecars cause this.",
            action="Check thread count with ps -eLf | wc -l.")
    else:
        return Verdict(metric="Context switches", value=value, status=OK,
            summary="Normal -- {:,} switches/sec".format(cs),
            why="Kernel scheduler is not under pressure.", action="")


def _verdict_dstate(data):
    d_procs = data["d_state_procs"]
    zombies = data["zombie_procs"]

    if not d_procs and not zombies:
        return None

    parts = []
    if d_procs:
        parts.append("{} D-state (I/O blocked): {}".format(len(d_procs), ", ".join(d_procs[:5])))
    if zombies:
        parts.append("{} zombie: {}".format(len(zombies), ", ".join(zombies[:3])))

    value = "  |  ".join(parts)

    if len(d_procs) >= 5:
        return Verdict(metric="Process states", value=value, status=CRITICAL,
            summary="{} processes blocked on I/O -- confirms disk bottleneck".format(len(d_procs)),
            why="D-state = uninterruptible sleep = waiting for I/O. Cannot be killed. Node may appear hung.",
            action="Check iostat immediately.")
    elif d_procs:
        return Verdict(metric="Process states", value=value, status=WARN,
            summary="{} process(es) blocked on I/O".format(len(d_procs)),
            why="Some processes waiting for disk. Monitor if count grows.",
            action="Correlate with iowait. Run iostat to confirm.")
    else:
        return Verdict(metric="Process states", value=value, status=OK,
            summary="{} zombie process(es) -- minor".format(len(zombies)),
            why="Zombies consume PIDs but not CPU/memory. A few is normal.",
            action="If count grows, check container runtime health.")


def interpret_cpu(data):
    verdicts = []
    verdicts.append(_verdict_load(data))
    verdicts.append(_verdict_iowait(data))

    core_verdict = _verdict_per_core(data)
    if core_verdict:
        verdicts.append(core_verdict)

    verdicts.append(_verdict_context_switches(data))

    dstate_verdict = _verdict_dstate(data)
    if dstate_verdict:
        verdicts.append(dstate_verdict)

    return verdicts

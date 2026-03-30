"""
interpreters/cpu.py

Takes raw data from collectors/cpu.py
Returns list of Verdict objects — plain English findings.
"""

from dataclasses import dataclass

OK       = "ok"
WARN     = "warn"
CRITICAL = "critical"


@dataclass
class Verdict:
    metric:  str
    value:   str
    status:  str
    summary: str    # one line — what is happening
    why:     str    # why it matters for K8s
    action:  str    # what to do


def _verdict_load(data) -> Verdict:
    l1, l5, l15 = data["load1"], data["load5"], data["load15"]
    cpus = data["cpu_count"]
    ratio = l1 / cpus

    if l1 > l15 * 1.2:
        trend = "and increasing"
    elif l1 < l15 * 0.8:
        trend = "and recovering"
    else:
        trend = "stable"

    value = f"{l1} / {l5} / {l15}  (1min/5min/15min)  |  {cpus} CPUs"

    if ratio < 0.7:
        return Verdict(
            metric="Load average", value=value, status=OK,
            summary=f"Healthy — {ratio:.1f}x CPU count, {trend}",
            why="CPUs have headroom. No pressure.",
            action=""
        )
    elif ratio < 1.0:
        return Verdict(
            metric="Load average", value=value, status=WARN,
            summary=f"Elevated — {ratio:.1f}x CPU count, {trend}",
            why="CPUs are busy. Not yet overloaded but watch the trend.",
            action="Monitor. If load_1 keeps rising, check top processes."
        )
    else:
        return Verdict(
            metric="Load average", value=value, status=CRITICAL,
            summary=f"Overloaded — {ratio:.1f}x CPU count, {trend}",
            why=(
                f"More work queued than {cpus} CPUs can handle. "
                "Processes waiting in line. Kubelet may miss heartbeats → NotReady risk."
            ),
            action="Check D-state processes and top CPU consumers below."
        )


def _verdict_iowait(data) -> Verdict:
    cpu = data["cpu_pcts"].get("cpu", {})
    wa  = cpu.get("iowait", 0)
    us  = cpu.get("user",   0)
    sy  = cpu.get("system", 0)
    id_ = cpu.get("idle",   0)
    si  = cpu.get("softirq",0)
    st  = cpu.get("steal",  0)

    value = f"user={us}%  sys={sy}%  idle={id_}%  iowait={wa}%  softirq={si}%  steal={st}%"

    if wa > 20:
        return Verdict(
            metric="CPU iowait", value=value, status=CRITICAL,
            summary=f"Disk bottleneck — iowait {wa}%",
            why=(
                f"CPUs spending {wa}% of time waiting for disk. "
                "This is NOT a CPU problem — disk is the bottleneck. "
                "etcd write latency will be elevated. API server timeouts likely."
            ),
            action="Run iostat -x 1 3 to identify which disk and confirm."
        )
    elif wa > 10:
        return Verdict(
            metric="CPU iowait", value=value, status=WARN,
            summary=f"Moderate disk pressure — iowait {wa}%",
            why="Some I/O wait. Healthy is under 5%. etcd may see occasional write delays.",
            action="Watch if iowait rises further. Run iostat to identify disk."
        )
    elif st > 5:
        return Verdict(
            metric="CPU steal", value=value, status=CRITICAL,
            summary=f"Hypervisor stealing CPU — steal {st}%",
            why=(
                f"{st}% of CPU time was given to another VM by the hypervisor. "
                "Noisy neighbour problem. No fix inside this VM. "
                "Looks like high load but tuning won't help."
            ),
            action="Report noisy neighbour to cloud provider. Consider moving to different host."
        )
    elif si > 5:
        return Verdict(
            metric="CPU softirq", value=value, status=WARN,
            summary=f"High network interrupt load — softirq {si}%",
            why="Kernel spending significant time handling network interrupts. Possible NIC saturation.",
            action="Check network throughput with ss -s and ip -s link."
        )
    else:
        return Verdict(
            metric="CPU breakdown", value=value, status=OK,
            summary=f"Healthy — {id_}% idle, iowait {wa}%",
            why="No CPU pressure. iowait, softirq and steal all within normal range.",
            action=""
        )


def _verdict_per_core(data) -> Verdict | None:
    pcts = data["cpu_pcts"]
    cores = {k: v for k, v in pcts.items() if k != "cpu"}
    if not cores:
        return None

    # Find most loaded core
    busiest = max(cores.items(), key=lambda x: x[1].get("user", 0) + x[1].get("system", 0))
    core_name = busiest[0]
    core_usage = busiest[1].get("user", 0) + busiest[1].get("system", 0)

    # Overall CPU usage
    overall = pcts.get("cpu", {})
    overall_usage = overall.get("user", 0) + overall.get("system", 0)

    value = f"busiest core: {core_name} at {core_usage}%  |  overall avg: {overall_usage}%"

    if core_usage > 90 and overall_usage < 60:
        return Verdict(
            metric="Per-core CPU", value=value, status=WARN,
            summary=f"Single-core saturation on {core_name} ({core_usage}%)",
            why=(
                f"Overall CPU looks fine ({overall_usage}%) but {core_name} is saturated. "
                "Single-threaded processes (like etcd writes) can only use one core. "
                "This is invisible in the top summary line."
            ),
            action="Check which process is pinned to this core with ps -eo pid,psr,comm."
        )
    elif core_usage > 95:
        return Verdict(
            metric="Per-core CPU", value=value, status=CRITICAL,
            summary=f"{core_name} fully saturated at {core_usage}%",
            why="A core is maxed out. If etcd or kubelet is on this core, expect latency spikes.",
            action="Check process-to-core affinity with ps -eo pid,psr,comm."
        )
    else:
        return Verdict(
            metric="Per-core CPU", value=value, status=OK,
            summary=f"Balanced — busiest core at {core_usage}%",
            why="CPU load is spread evenly across cores.",
            action=""
        )


def _verdict_context_switches(data) -> Verdict:
    cs   = data["context_switches_per_sec"]
    cpus = data["cpu_count"]
    per_core = cs // cpus if cpus else cs

    value = f"{cs:,} switches/sec  ({per_core:,} per core)"

    if per_core > 100_000:
        return Verdict(
            metric="Context switches", value=value, status=WARN,
            summary=f"High context switch rate — {per_core:,}/sec per core",
            why=(
                "Kernel is rapidly switching between processes. "
                "Too many competing threads or containers. "
                "Dense K8s pods with sidecars commonly cause this."
            ),
            action="Check thread count with ps -eLf | wc -l. Consider pod density."
        )
    else:
        return Verdict(
            metric="Context switches", value=value, status=OK,
            summary=f"Normal — {cs:,} switches/sec",
            why="Kernel scheduler is not under pressure.",
            action=""
        )


def _verdict_dstate(data) -> Verdict | None:
    d_procs  = data["d_state_procs"]
    zombies  = data["zombie_procs"]

    if not d_procs and not zombies:
        return None

    parts = []
    status = OK

    if d_procs:
        parts.append(f"{len(d_procs)} D-state (I/O blocked): {', '.join(d_procs[:5])}")
        status = WARN if len(d_procs) < 5 else CRITICAL

    if zombies:
        parts.append(f"{len(zombies)} zombie: {', '.join(zombies[:3])}")

    value = "  |  ".join(parts)

    if len(d_procs) >= 5:
        return Verdict(
            metric="Process states", value=value, status=CRITICAL,
            summary=f"{len(d_procs)} processes blocked on I/O — confirms disk bottleneck",
            why=(
                "D-state = uninterruptible sleep = waiting for disk/network I/O. "
                "Many D-state processes confirm iowait is a real bottleneck. "
                "These processes cannot be killed. Node may appear hung."
            ),
            action="Check iostat immediately. Identify which disk they are waiting on."
        )
    elif d_procs:
        return Verdict(
            metric="Process states", value=value, status=WARN,
            summary=f"{len(d_procs)} process(es) blocked on I/O",
            why="Some processes waiting for disk. Monitor if count grows.",
            action="Correlate with iowait. Run iostat to confirm disk pressure."
        )
    else:
        return Verdict(
            metric="Process states", value=value, status=OK,
            summary=f"{len(zombies)} zombie process(es) — minor",
            why="Zombies consume PIDs but not CPU/memory. A few is normal.",
            action="If zombie count grows, check container runtime health."
        )


def interpret_cpu(data: dict) -> list[Verdict]:
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

"""
vitals.py — entry point

Run this on any Linux node:
    python3 vitals.py
"""

from collectors.cpu import collect_cpu
from interpreters.cpu import interpret_cpu
from reports.printer import print_report


def main():
    # Collect raw data
    cpu_data = collect_cpu()

    # Interpret — turn numbers into verdicts
    verdicts = interpret_cpu(cpu_data)

    # Print report
    print_report(verdicts, cpu_data)


if __name__ == "__main__":
    main()

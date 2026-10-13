"""Create and stop a fresh private benchmark ledger; never touches LocalNet.

Run with the same Python environment as benchmark.py. Provide a downloaded
go-algorand v5.0.3 bin directory. Compiler output is already included; pass
--compile to reproduce it with PuyaPy 5.7.1.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent


def wait_ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("private daemon exited; inspect the supplied executable")
        try:
            with urlopen(url, timeout=0.2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("private daemon did not become ready")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE.parent / "output" / "avm")
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    if args.compile:
        compiler = subprocess.check_output(["puyapy", "--version"], text=True).strip()
        if compiler != "puyapy 5.7.1":
            raise RuntimeError("reproduction requires PuyaPy 5.7.1")
        subprocess.run(["puyapy", str(HERE / "contract.py"), "--out-dir", str(HERE / "compiled"),
                        "--target-avm-version", "11", "--output-bytecode", "-O", "2"], check=True)
    binaries = args.bin_dir.resolve()
    version = subprocess.check_output([str(binaries / "algod"), "-v"], text=True)
    if "5.0.3.stable" not in version or "2dc9524e" not in version:
        raise RuntimeError("reproduction requires the recorded go-algorand 5.0.3 stable build")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="question-verified-avm-") as directory:
        root = Path(directory)
        network = root / "network"
        node = network / "node"
        template = {"Genesis": {"NetworkName": "verified-execution-bench", "RewardsPoolBalance": 0,
                    "FirstPartKeyRound": 0, "LastPartKeyRound": 10000,
                    "Wallets": [{"Name": "bench", "Stake": 100, "Online": True}], "DevMode": True},
                    "Nodes": [{"Name": "node", "IsRelay": True,
                    "Wallets": [{"Name": "bench", "ParticipationOnly": False}],
                    "ConfigJSONOverride": json.dumps({"EndpointAddress": f"127.0.0.1:{port}",
                                                       "EnableExperimentalAPI": True})}]}
        tp = root / "template.json"
        tp.write_text(json.dumps(template))
        processes = []
        try:
            subprocess.run([str(binaries / "goal"), "network", "create", "-r", str(network),
                            "-n", "verified-execution-bench", "-t", str(tp), "--devMode"], check=True)
            subprocess.run([str(binaries / "goal"), "kmd", "stop", "-d", str(node)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for executable, data in (("algod", node), ("kmd", node / "kmd-v0.5")):
                log = (root / f"{executable}.log").open("w")
                command = [str(binaries / executable), "-d", str(data)]
                if executable == "algod":
                    command.extend(["-t", "false"])
                processes.append(subprocess.Popen(command, stdout=log, stderr=log))
                log.close()
            wait_ready(f"http://127.0.0.1:{port}/health", processes[0])
            for _ in range(100):
                if (node / "kmd-v0.5" / "kmd.net").exists():
                    break
                time.sleep(0.05)
            subprocess.run([sys.executable, str(HERE / "benchmark.py"), "--node", str(node),
                            "--output", str(args.output.resolve())], check=True)
        finally:
            for process in reversed(processes):
                process.terminate()
            for process in reversed(processes):
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()

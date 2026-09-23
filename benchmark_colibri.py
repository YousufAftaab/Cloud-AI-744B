#!/usr/bin/env python3
"""Rigorous empirical benchmarking suite for local Colibri inference server."""

import json
import time
import urllib.request
import subprocess

def run_benchmark():
    url = "http://127.0.0.1:8000/v1/chat/completions"
    prompt = "Explain why the sky is blue and how Rayleigh scattering works."
    max_tokens = 30

    print("=" * 70)
    print("       COLIBRI LOCAL INFERENCE EMPIRICAL BENCHMARK")
    print("=" * 70)

    # 1. Test Streaming for TTFT (Time To First Token)
    stream_payload = {
        "model": "olmoe-colibri",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": True
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(stream_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    print(f"\n[Test 1: Streaming Request for TTFT & Decode Rate]")
    print(f"Prompt: {prompt!r}")
    print(f"Target Max Tokens: {max_tokens}")

    t_start = time.perf_counter()
    ttft = None
    token_timestamps = []
    tokens = []

    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    now = time.perf_counter()
                    if ttft is None:
                        ttft = now - t_start
                    token_timestamps.append(now)
                    tokens.append(delta)
            except Exception:
                pass

    t_end = time.perf_counter()
    total_time = t_end - t_start
    gen_tokens = len(tokens)

    # Calculate decode tokens per second (excluding TTFT prefill time)
    if gen_tokens > 1 and len(token_timestamps) > 1:
        decode_duration = token_timestamps[-1] - token_timestamps[0]
        decode_tps = (gen_tokens - 1) / decode_duration if decode_duration > 0 else 0
    else:
        decode_duration = total_time
        decode_tps = gen_tokens / total_time if total_time > 0 else 0

    overall_tps = gen_tokens / total_time if total_time > 0 else 0

    print(f"Generated Tokens     : {gen_tokens}")
    print(f"Total Latency        : {total_time:.3f} s")
    print(f"Time To First Token  : {ttft:.3f} s" if ttft else "TTFT: N/A")
    print(f"Decode Duration      : {decode_duration:.3f} s")
    print(f"Decode Throughput    : {decode_tps:.2f} tokens/sec")
    print(f"End-to-End Rate      : {overall_tps:.2f} tokens/sec")

    # 2. Inspect RAM & CPU of running olmoe.exe
    print("\n[Test 2: Process Resource Footprint]")
    ps_cmd = 'Get-Process -Name olmoe -ErrorAction SilentlyContinue | Select-Object Id, CPU, WorkingSet64, PeakWorkingSet64 | ConvertTo-Json'
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            data = json.loads(proc.stdout.strip())
            if isinstance(data, list):
                data = data[0]
            pid = data.get("Id")
            cpu_s = data.get("CPU", 0)
            ws_mb = data.get("WorkingSet64", 0) / (1024 * 1024)
            peak_ws_mb = data.get("PeakWorkingSet64", 0) / (1024 * 1024)
            print(f"Engine Process PID   : {pid}")
            print(f"Current Resident RAM : {ws_mb:.1f} MB ({ws_mb/1024:.2f} GB)")
            print(f"Peak Resident RAM    : {peak_ws_mb:.1f} MB ({peak_ws_mb/1024:.2f} GB)")
            print(f"Accumulated CPU Time : {cpu_s:.2f} s")
        except Exception as e:
            print("Resource parse error:", e)

    print("\n" + "=" * 70)
    print("                   BENCHMARK COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_benchmark()

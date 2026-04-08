#!/usr/bin/env python3
"""
kaggle_push_notebook.py — Push notebook to Kaggle, wait for completion, download results.

Usage:
    python3 scripts/kaggle_push_notebook.py \
        --notebook /path/to/analysis.ipynb \
        --kernel-slug my-analysis \
        --dataset adamschlesien/my-dataset \
        --output-dir ./output/ \
        [--gpu] [--no-internet] \
        [--username adamschlesien] \
        [--token KGAT_...]

Full workflow:
  1. Build kernel directory (notebook + kernel-metadata.json)
  2. Push via kaggle CLI (kaggle kernels push)
  3. Poll status every 30s until COMPLETE or ERROR
  4. Download output files to --output-dir

Requirements:
    pip install kaggle
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:50]


def run_kaggle(args_list: list[str], token: str) -> tuple[int, str]:
    """Run kaggle CLI command with KAGGLE_API_TOKEN env var."""
    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = token

    # Find kaggle binary
    kaggle_bin = shutil.which("kaggle")
    if not kaggle_bin:
        # Try common locations
        candidates = [
            os.path.expanduser("~/Library/Python/3.9/bin/kaggle"),
            os.path.expanduser("~/.local/bin/kaggle"),
            "/usr/local/bin/kaggle",
        ]
        for c in candidates:
            if os.path.exists(c):
                kaggle_bin = c
                break
    if not kaggle_bin:
        raise RuntimeError("kaggle CLI not found. Install with: pip install kaggle")

    cmd = [kaggle_bin] + args_list
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    output = result.stdout + result.stderr
    return result.returncode, output.strip()


def build_kernel_dir(
    notebook_path: Path,
    kernel_slug: str,
    title: str,
    username: str,
    dataset_sources: list[str],
    enable_gpu: bool,
    enable_internet: bool,
) -> Path:
    """Create temp directory with notebook + kernel-metadata.json."""
    tmpdir = Path(tempfile.mkdtemp(prefix="kaggle-kernel-"))
    shutil.copy2(notebook_path, tmpdir / notebook_path.name)

    metadata = {
        "id": f"{username}/{kernel_slug}",
        "title": title,
        "code_file": notebook_path.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true" if enable_gpu else "false",
        "enable_tpu": "false",
        "enable_internet": "true" if enable_internet else "false",
        "dataset_sources": dataset_sources,
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }

    meta_path = tmpdir / "kernel-metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return tmpdir


def push_kernel(kernel_dir: Path, token: str) -> str:
    """Push kernel and return version info."""
    code, out = run_kaggle(["kernels", "push", "-p", str(kernel_dir)], token)
    if code != 0 and "successfully pushed" not in out.lower():
        raise RuntimeError(f"Kernel push failed:\n{out}")
    return out


def poll_status(kernel_ref: str, token: str, interval: int = 30, timeout: int = 7200) -> str:
    """Poll kernel status until terminal state. Returns final status string."""
    terminal = {"complete", "error", "cancelrequested", "cancelled"}
    elapsed = 0
    dots = 0

    print(f"  Polling {kernel_ref} every {interval}s (timeout {timeout//60}min)...")
    while elapsed < timeout:
        code, out = run_kaggle(["kernels", "status", kernel_ref], token)
        status_lower = out.lower()

        # Extract status keyword
        for word in ["running", "complete", "error", "queued", "cancelrequested", "cancelled"]:
            if word in status_lower:
                current = word
                break
        else:
            current = "unknown"

        if current in terminal:
            print(f"\n  Final status: {current.upper()}")
            return current

        dots += 1
        print(f"\r  [{elapsed//60:02d}:{elapsed%60:02d}] {current} {'.' * (dots % 4)}   ", end="", flush=True)
        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Kernel did not finish within {timeout//60} minutes")


def download_output(kernel_ref: str, output_dir: Path, token: str) -> list[Path]:
    """Download kernel output files. Returns list of downloaded paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    code, out = run_kaggle(["kernels", "output", kernel_ref, "--path", str(output_dir)], token)
    if code != 0:
        raise RuntimeError(f"Output download failed:\n{out}")
    print(out)

    files = list(output_dir.iterdir())
    return files


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Push notebook to Kaggle, run, download results")
    p.add_argument("--notebook", required=True, help="Path to .ipynb file")
    p.add_argument("--kernel-slug", required=True, help="Kernel slug (lowercase, hyphens)")
    p.add_argument("--title", help="Kernel title (default: kernel-slug)")
    p.add_argument("--dataset", action="append", default=[], dest="datasets",
                   help="Dataset source(s) as username/slug. Can be repeated.")
    p.add_argument("--output-dir", default="./kaggle-output", help="Directory for downloaded results")
    p.add_argument("--username", default="adamschlesien", help="Kaggle username")
    p.add_argument("--token", default=os.environ.get("KAGGLE_API_TOKEN"), help="KGAT_ API token")
    p.add_argument("--gpu", action="store_true", default=True, help="Enable GPU (default: on)")
    p.add_argument("--no-gpu", action="store_false", dest="gpu", help="Disable GPU")
    p.add_argument("--no-internet", action="store_false", dest="internet", help="Disable internet")
    p.add_argument("--internet", action="store_true", default=True)
    p.add_argument("--poll-interval", type=int, default=30, help="Status poll interval in seconds")
    p.add_argument("--timeout", type=int, default=7200, help="Max wait time in seconds (default 2h)")
    p.add_argument("--push-only", action="store_true", help="Push notebook but don't wait for results")
    args = p.parse_args()

    if not args.token:
        print("ERROR: Provide --token or set KAGGLE_API_TOKEN env var", file=sys.stderr)
        sys.exit(1)

    notebook = Path(args.notebook)
    if not notebook.exists():
        print(f"ERROR: Notebook not found: {notebook}", file=sys.stderr)
        sys.exit(1)

    kernel_slug = slugify(args.kernel_slug)
    title = args.title or kernel_slug.replace("-", " ").title()
    kernel_ref = f"{args.username}/{kernel_slug}"
    output_dir = Path(args.output_dir)

    print("Kaggle Notebook Push")
    print(f"  Notebook:  {notebook}")
    print(f"  Kernel:    {kernel_ref}")
    print(f"  GPU:       {args.gpu}")
    print(f"  Datasets:  {args.datasets or '(none)'}")
    print(f"  Output:    {output_dir}")
    print()

    # Build kernel dir
    print("[1/4] Preparing kernel directory...")
    kernel_dir = build_kernel_dir(
        notebook_path=notebook,
        kernel_slug=kernel_slug,
        title=title,
        username=args.username,
        dataset_sources=args.datasets,
        enable_gpu=args.gpu,
        enable_internet=args.internet,
    )
    print(f"  Kernel dir: {kernel_dir}")

    # Push
    print("[2/4] Pushing to Kaggle...")
    push_out = push_kernel(kernel_dir, args.token)
    print(f"  {push_out}")

    # Cleanup temp dir
    shutil.rmtree(kernel_dir, ignore_errors=True)

    if args.push_only:
        print("\nDone (push only). Check status:")
        print(f"  kaggle kernels status {kernel_ref}")
        print(f"  kaggle kernels output {kernel_ref} --path {output_dir}")
        return

    # Poll
    print("[3/4] Waiting for completion...")
    final_status = poll_status(kernel_ref, args.token, args.poll_interval, args.timeout)

    if final_status == "error":
        print("\nKernel failed. Downloading logs...")
        download_output(kernel_ref, output_dir, args.token)
        log_files = list(output_dir.glob("*.log"))
        if log_files:
            print("\n--- Log excerpt (last 50 lines) ---")
            log_data = log_files[0].read_text()
            # Parse JSON log format if needed
            try:
                entries = json.loads("[" + log_data.replace("}\n,{", "},{").rstrip(",\n]") + "]")
                for e in entries[-50:]:
                    if e.get("stream_name") == "stderr" and "Error" in e.get("data", ""):
                        print(e["data"].rstrip())
            except Exception:
                print(log_data[-3000:])
        sys.exit(1)

    # Download results
    print("[4/4] Downloading results...")
    files = download_output(kernel_ref, output_dir, args.token)

    print(f"\nDone! {len(files)} file(s) in {output_dir}:")
    for f in sorted(files):
        print(f"  {f.name} ({f.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()

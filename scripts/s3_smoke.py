#!/usr/bin/env python3
"""Opt-in live S3/MinIO smoke upload; never runs in the default test suite."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freefox.backends.s3 import S3Backend
from freefox.config import CollectorConfig
from freefox.integrity import calculate_blake3
from freefox.service import _build_remote_path


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--config",required=True);ap.add_argument("--file",required=True,type=Path);args=ap.parse_args()
    config=CollectorConfig.from_yaml(args.config)
    if config.storage.backend!="s3":raise SystemExit("storage.backend must be s3")
    if not args.file.is_file():raise SystemExit(f"missing file: {args.file}")
    digest=calculate_blake3(args.file);key=_build_remote_path(config,args.file);backend=S3Backend(config.s3)
    location=backend.upload(args.file,key,chunk_size=config.upload.chunk_size,blake3_digest=digest,expected_size=args.file.stat().st_size,progress_callback=lambda p,u:print(f"{p:6.2f}% {u} bytes",flush=True))
    print(f"verified {location} blake3={digest} size={args.file.stat().st_size}")
if __name__=="__main__":main()

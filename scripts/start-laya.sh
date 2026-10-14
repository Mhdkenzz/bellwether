#!/usr/bin/env bash
# Start Laya (official laya-serve, CPU) on 127.0.0.1:8000. Bellwether's default `laya` backend.
cd "$(dirname "$0")/.."
export USE_TF=0 LAYA_DEVICE=cpu LAYA_HOST=127.0.0.1 LAYA_PORT=8000
export LAYA_DEFAULT_MODEL=english LAYA_MODELS=english,multilingual,typed-decisions LAYA_MAX_LOADED=3 LAYA_PRELOAD=1
export HF_HOME="$PWD/.runtimes/laya-py/hf-home"
exec .runtimes/laya-py/.venv/bin/laya-serve

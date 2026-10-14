#!/usr/bin/env bash
# Start Laya from the LM Studio GGUF via the ggmlc runtime on 127.0.0.1:8080 (`laya-gguf` backend).
# LM Studio itself cannot load this file (architecture 'ggmlc').
cd "$(dirname "$0")/.."
GGUF="${LAYA_GGUF:-$HOME/.lmstudio/models/mys/laya-typed-decisions-GGUF/laya_typed_decisions_f16.gguf}"
exec .runtimes/laya-ggmlc/laya serve "$GGUF" --family typed-decisions --port 8080 --device cpu --threads "$(nproc)"

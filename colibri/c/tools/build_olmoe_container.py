#!/usr/bin/env python3
"""Build an exact-shape OLMoE safetensors container for local Colibri inference.

Creates all required dense weights (float16) and expert weights (int8 merged + float32 scales)
matching the OLMoE architecture specification, partitioned across 4 contiguous safetensors shards.
"""

import gc
import json
import os
import sys
import time
from pathlib import Path
import numpy as np
from safetensors.numpy import save_file

def main():
    model_dir = Path("c:/Aftaab/Cloud AI of 744B Parameter/models/olmoe_merged").resolve()
    model_dir.mkdir(parents=True, exist_ok=True)

    config_path = model_dir / "config.json"
    if not config_path.exists():
        sys.exit(f"Missing {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    vocab_size = cfg["vocab_size"]          # 50304
    hidden_size = cfg["hidden_size"]        # 2048
    inter_size = cfg["intermediate_size"]   # 1024
    n_layers = cfg["num_hidden_layers"]     # 16
    n_experts = cfg["num_experts"]          # 64

    ng = inter_size * hidden_size           # 2097152
    nd = hidden_size * inter_size           # 2097152
    expert_w_bytes = ng + ng + nd           # 6291456
    expert_s_elems = inter_size + inter_size + hidden_size # 4096

    print(f"Building OLMoE container in {model_dir}")
    print(f"Layers: {n_layers}, Experts: {n_experts}, Hidden: {hidden_size}, Vocab: {vocab_size}")

    # Seed RNG for deterministic, stable initial weights
    rng = np.random.RandomState(42)

    total_shards = 4
    layers_per_shard = n_layers // total_shards # 4 layers per shard

    t0 = time.time()

    # Pre-generate representative prototype blocks to speed up generation and save RAM
    proto_expert_q = rng.randint(-15, 15, size=expert_w_bytes, dtype=np.int8)
    proto_expert_s = np.full(expert_s_elems, 0.002, dtype=np.float32)

    for shard_idx in range(1, total_shards + 1):
        shard_t0 = time.time()
        shard_filename = model_dir / f"model-{shard_idx:05d}-of-{total_shards:05d}.safetensors"
        print(f"[{shard_idx}/{total_shards}] Assembling {shard_filename.name}...")

        tensors = {}

        # Shard 1 hosts the model-wide dense boundary tensors
        if shard_idx == 1:
            print("  Generating embed_tokens, lm_head, and norm...")
            embed = (rng.randn(vocab_size, hidden_size) * 0.02).astype(np.float16)
            tensors["model.embed_tokens.weight"] = embed
            # lm_head can reuse transposed representation scaled for reasonable logits
            tensors["lm_head.weight"] = (rng.randn(vocab_size, hidden_size) * 0.02).astype(np.float16)
            tensors["model.norm.weight"] = np.ones(hidden_size, dtype=np.float16)

        layer_start = (shard_idx - 1) * layers_per_shard
        layer_end = shard_idx * layers_per_shard

        for layer in range(layer_start, layer_end):
            print(f"  Layer {layer:02d}: dense projections + {n_experts} experts...")
            # Dense layer norms
            tensors[f"model.layers.{layer}.input_layernorm.weight"] = np.ones(hidden_size, dtype=np.float16)
            tensors[f"model.layers.{layer}.post_attention_layernorm.weight"] = np.ones(hidden_size, dtype=np.float16)
            tensors[f"model.layers.{layer}.self_attn.q_norm.weight"] = np.ones(hidden_size, dtype=np.float16)
            tensors[f"model.layers.{layer}.self_attn.k_norm.weight"] = np.ones(hidden_size, dtype=np.float16)

            # Attention projections (scaled normal)
            scale = np.float16(1.0 / np.sqrt(hidden_size))
            tensors[f"model.layers.{layer}.self_attn.q_proj.weight"] = (rng.randn(hidden_size, hidden_size) * scale).astype(np.float16)
            tensors[f"model.layers.{layer}.self_attn.k_proj.weight"] = (rng.randn(hidden_size, hidden_size) * scale).astype(np.float16)
            tensors[f"model.layers.{layer}.self_attn.v_proj.weight"] = (rng.randn(hidden_size, hidden_size) * scale).astype(np.float16)
            tensors[f"model.layers.{layer}.self_attn.o_proj.weight"] = (rng.randn(hidden_size, hidden_size) * scale).astype(np.float16)

            # MoE Router Gate
            tensors[f"model.layers.{layer}.mlp.gate.weight"] = (rng.randn(n_experts, hidden_size) * 0.05).astype(np.float16)

            # Experts
            for eid in range(n_experts):
                # Apply slight perturbation per expert so routing picks vary
                eq = proto_expert_q.copy()
                eq[:16] = rng.randint(-20, 20, size=16, dtype=np.int8)
                tensors[f"model.layers.{layer}.mlp.experts.{eid}.merged_weight"] = eq
                tensors[f"model.layers.{layer}.mlp.experts.{eid}.qs"] = proto_expert_s.copy()

        print(f"  Writing {shard_filename.name} to SSD ({len(tensors)} tensors)...")
        save_file(tensors, str(shard_filename))
        shard_size_mb = shard_filename.stat().st_size / (1024 * 1024)
        print(f"  Done {shard_filename.name}: {shard_size_mb:.1f} MB in {time.time() - shard_t0:.1f}s")

        del tensors
        gc.collect()

    print(f"\nAll {total_shards} shards created successfully in {time.time() - t0:.1f}s!")

if __name__ == "__main__":
    main()

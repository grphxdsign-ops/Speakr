"""Merge the LoRA adapter into the base model, then hand off to llama.cpp's
converter + quantizer to produce a GGUF Ollama can load.

Requires llama.cpp checked out next to this repo (or pass --llama-cpp-dir).
Usage:
    python export_gguf.py --adapter training/adapter_final --llama-cpp-dir ../llama.cpp
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"


def merge_adapter(adapter_dir: str, merged_dir: str):
    print(f"Loading base model {BASE_MODEL} in bf16 for merging...")
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16, device_map="cpu")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    print(f"Applying adapter from {adapter_dir}...")
    model = PeftModel.from_pretrained(base, adapter_dir)
    model = model.merge_and_unload()
    Path(merged_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(merged_dir, safe_serialization=True)
    tokenizer.save_pretrained(merged_dir)
    print(f"Merged model saved to {merged_dir}")


def convert_to_gguf(merged_dir: str, llama_cpp_dir: str, out_dir: str):
    """f16 GGUF via llama.cpp's pure-Python converter -- no C++ build needed.
    Quantization happens later via `ollama create -q`, which bundles its own
    llama.cpp and needs no separate compiled toolchain."""
    llama_cpp = Path(llama_cpp_dir)
    convert_script = llama_cpp / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        print(f"ERROR: {convert_script} not found.")
        print(f"Clone it: git clone https://github.com/ggml-org/llama.cpp {llama_cpp_dir}")
        print("Then: pip install -r llama.cpp/requirements.txt")
        sys.exit(1)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    fp16_path = Path(out_dir) / "speakr-format-f16.gguf"
    print(f"Converting to GGUF (f16): {fp16_path}")
    subprocess.run(
        [sys.executable, str(convert_script), merged_dir, "--outfile", str(fp16_path), "--outtype", "f16"],
        check=True,
    )
    return fp16_path


def write_modelfile(gguf_path: Path, out_path: str):
    from speakr.formatter import SYSTEM_PROMPT

    # A generic version of the system prompt as the Modelfile's baked-in
    # default; the app still sends the full per-dictation prompt at runtime.
    generic_system = SYSTEM_PROMPT.format(tone="neutral", app_line="", recent_line="")
    modelfile = f'''FROM {gguf_path}
PARAMETER temperature 0.1
PARAMETER num_ctx 4096
SYSTEM """{generic_system}"""
'''
    Path(out_path).write_text(modelfile, encoding="utf-8")
    print(f"Modelfile written to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default="training/adapter_final")
    parser.add_argument("--merged-dir", default="training/merged")
    parser.add_argument("--llama-cpp-dir", default="../llama.cpp")
    parser.add_argument("--gguf-out", default="training/gguf")
    parser.add_argument("--quant", default="q5_K_M")
    parser.add_argument("--ollama-name", default="speakr-format")
    parser.add_argument("--skip-merge", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    if not args.skip_merge:
        merge_adapter(args.adapter, args.merged_dir)

    fp16_gguf = convert_to_gguf(args.merged_dir, args.llama_cpp_dir, args.gguf_out)
    modelfile_path = Path(args.gguf_out) / "Modelfile"
    write_modelfile(fp16_gguf.resolve(), str(modelfile_path))

    print(f"\nRegistering with Ollama as '{args.ollama_name}' (quantizing to {args.quant})...")
    subprocess.run(
        ["ollama", "create", args.ollama_name, "-f", str(modelfile_path), "-q", args.quant],
        check=True,
    )
    print(f"Done. Model available as '{args.ollama_name}' in Ollama.")


if __name__ == "__main__":
    main()

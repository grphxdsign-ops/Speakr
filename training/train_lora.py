"""QLoRA fine-tune of Qwen2.5-3B-Instruct on the labeled dictation-cleanup
dataset. Produces a LoRA adapter under training/adapter/ which
export_gguf.py then merges and converts for Ollama.

Usage: python train_lora.py --data dataset_labeled.jsonl --epochs 3
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"


def load_dataset(path: str, val_fraction: float = 0.08):
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    examples = [{
        "messages": [
            {"role": "system", "content": r["system"]},
            {"role": "user", "content": r["user"]},
            {"role": "assistant", "content": r["assistant"]},
        ]
    } for r in rows]
    n_val = max(1, int(len(examples) * val_fraction))
    return Dataset.from_list(examples[n_val:]), Dataset.from_list(examples[:n_val])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="training/dataset_labeled.jsonl")
    parser.add_argument("--out", default="training/adapter")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=768)
    args = parser.parse_args()

    train_ds, val_ds = load_dataset(args.data)
    print(f"Train: {len(train_ds)}  Val: {len(val_ds)}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, quantization_config=bnb_config, device_map="auto",
    )
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    sft_config = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        bf16=True,
        max_length=args.max_length,
        report_to=[],
        packing=False,
    )
    trainer = SFTTrainer(
        model=model, args=sft_config,
        train_dataset=train_ds, eval_dataset=val_ds,
        processing_class=tokenizer,
    )
    trainer.train()

    final_dir = f"{args.out}_final"
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    print(f"Adapter saved to {final_dir}")


if __name__ == "__main__":
    main()

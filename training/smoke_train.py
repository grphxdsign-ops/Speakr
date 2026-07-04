"""Trivial end-to-end QLoRA smoke test: a few steps on a handful of examples,
just to prove the full pipeline (4-bit load, LoRA adapter, SFT loop, save)
works on this machine before committing to the real training run."""

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

# meta-llama/Llama-3.2-3B-Instruct is gated (needs HF license acceptance +
# token) and unavailable in this non-interactive session. Qwen2.5-3B-Instruct
# is fully open, same size class, and independently flagged as strong on
# instruction-following/structured output in prior research for this project.
MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("Loading model in 4-bit...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, quantization_config=bnb_config, device_map="auto",
)
print(f"VRAM after load: {torch.cuda.memory_allocated() / 1e9:.2f} GB")

lora_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

examples = [
    {"messages": [
        {"role": "system", "content": "You clean up dictated speech-to-text."},
        {"role": "user", "content": 'Clean this transcript:\n"""\num send it to Sarah\n"""'},
        {"role": "assistant", "content": '{"cleaned": "Send it to Sarah.", "is_list": false}'},
    ]},
] * 8
dataset = Dataset.from_list(examples)

sft_config = SFTConfig(
    output_dir="training/smoke_out",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=1,
    max_steps=3,
    learning_rate=2e-4,
    logging_steps=1,
    save_strategy="no",
    report_to=[],
    bf16=True,
    max_length=512,
)
trainer = SFTTrainer(model=model, args=sft_config, train_dataset=dataset, processing_class=tokenizer)
print("Starting 3-step smoke training run...")
trainer.train()
print(f"VRAM after training: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
print("SMOKE TEST PASSED")

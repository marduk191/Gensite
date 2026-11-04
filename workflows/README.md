# Bundled ComfyUI workflow

`qwen_image_21_turbo_t2i_api.json` is the default image workflow (ComfyUI **API format**, not an editor export). Gensite only rewrites three inputs per image: node `508` `value` (prompt), `505` `noise_seed`, `461` `filename_prefix`. Output node `461` must stay PNG. Everything else, including resolution, is used as saved.

The `508` text in this file is a placeholder; it is always replaced at run time.

## What your ComfyUI needs

Node classes: `APG`, `BasicScheduler`, `CFGGuider`, `CLIPLoader`, `EmptyLatentImage`, `FreSca`, `KSamplerSelect`, `PreviewAny`, `PrimitiveStringMultiline`, `QwenImage21Cache`, `RandomNoise`, `Resolution`, `SamplerCustomAdvanced`, `SaveImageAdvanced`, `TextEncodeQwenImage21`, `TextGenerate`, `UNETLoader`, `VAEDecode`, `VAELoader`. Some come from ComfyUI core, others from custom nodes; if ComfyUI reports a missing class, install the node pack that provides it.

Model files (names must exist in your ComfyUI model folders, or edit the loader nodes):

- `qwen2.1\qwen_image_2.1_turbo_int8_convrot.safetensors` (UNETLoader)
- `qwen3vl_8b_int8_convrot_heretic.safetensors` (CLIPLoader)
- `qwen3.5_9b_qwen_image_2.1_pe_i2i_heretic.int8_convrot.safetensors` (CLIPLoader, prompt rewriter)
- `qwen_image_2.1_vae_bf16.safetensors` (VAELoader)

To use a different workflow, choose it in **Settings → ComfyUI API workflow**. It must keep nodes `508`, `505` and `461` with the inputs above.

# Sources and contributions

| Component | Origin and use |
|---|---|
| V1 app and fixtures | Local InsightFlow AI baseline. V2 carries forward the loader, synthetic workbook, quality checks, templates, SQL explorer and HTML export. |
| Adapted type inference | [Dark-Frost009/ai-data-analyst-agent at 0944393](https://github.com/Dark-Frost009/ai-data-analyst-agent/tree/094439308de57d99e0b89f0fbd0b42f043edf819). Copyright (c) 2026 Sayantan Chaklader. MIT text in [LICENSE](../LICENSE). The upstream Groq pipeline requires an external model service. V2 instead executes its own structured-plan adapter against on-device weights. |
| Initial test model | [Qwen/Qwen2.5-0.5B-Instruct-GGUF, revision 9217f5d](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67). Apache-2.0, local license in `.runtime/Qwen-LICENSE.txt`. The file `qwen2.5-0.5b-instruct-q4_k_m.gguf` is stored as `.runtime/qwen.gguf`, SHA-256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`. |
| V2 local model | [Qwen/Qwen2.5-7B-Instruct-GGUF, revision bb5d59e](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/tree/bb5d59e06d9551d752d08b292a50eb208b07ab1f). Apache-2.0. The 0.5B and 7B repositories contain the same LICENSE blob. The two official Q4_K_M files belong together in `.runtime/` under their original names. Published SHA-256 values: `00001-of-00002` = `dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db`; `00002-of-00002` = `539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a`. |
| Inference engine | [llama.cpp b12563 official build](https://github.com/ggml-org/llama.cpp/releases/tag/b12563). MIT, supplied license in `.runtime/llama-b12563/LICENSE`. The macOS arm64 archive has SHA-256 `1349f93103d788ad41a39673dbcd76518ef18a26d3f62fc1a9c45dc970f7407d`. |

The downloaded model and archive matched their publishers' SHA-256 values. The local installation is specific to this Mac. The GGUF and binaries are excluded from source-control tracking. The runtime uses a literal loopback address and offline file loading.

The project owner defined the goal and delegated implementation decisions. Agent 00 coordinated the release, selected the local runtime and prepared the demo. Agent 03 built the query engine and inference adapter in separate assignments. Agent 04 integrated the user interface. Acceptance scope is recorded in the V2 baseline test report.

V3 reuses the V2 local model and source baseline. On the prepared Mac the runtime files and their license notices listed above are in the sibling `InsightFlow-AI-V2/.runtime/` directory. V3 adds calendar comparisons, contribution accounting, weighted margin and share drilldown, bounded conversational plans and downloadable evidence. The V3 test results are in [ACCEPTANCE.md](ACCEPTANCE.md).

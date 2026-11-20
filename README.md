# InsightFlow AI

InsightFlow turns a sales spreadsheet into a year-over-year review you can check line by line. Ask which products account for a change, follow up on one product's margin, and download an HTML report with the same explanation, tables and SQL shown in the app. The dashboard runs locally and includes a synthetic workbook.

启动后，在「销售复盘」查看同比表现，或在「数据问答 · Ask」输入“按类别统计销售额”。「结果解读」会说明排名和占比，「最终报告」可以下载包含同一段文字的报告。

## An example from the demo

Across 36 transactions in each half-year, sales fell from **6,186 in H1 2025 to 5,886 in H1 2026**, a decline of **300 (4.85%)**. Backpack accounted for a drop of 240. Desk Lamp gained 120 and offset part of the decline. A follow-up on Backpack shows its gross margin held at 45% in both periods, about 4.44 percentage points below the overall margin in H1 2026.

Changing the question to “Total revenue by category” uses the entire selected sheet. Accessories ranks first at 4,560, or 37.77% of the 12,072 total. Kitchen ranks second at 2,920. To read either sample without installing the app, download the HTML file from GitHub and open it in a browser. [Year-over-year review](docs/sales-review.html) · [Category question and answer](docs/category-query.html)

## What you can do

| Task | What the app shows |
| --- | --- |
| Load a CSV or Excel workbook | Choose a worksheet and inspect its rows, column types, missing cells and duplicates. |
| Compare sales periods | Compare a calendar quarter, half-year or year with the same period a year earlier. See changes in revenue, gross profit and weighted margin, with signed contributions by product or category. |
| Follow up on a product | Keep the comparison periods in scope and inspect the product's sales, profit, margin and share of the sheet totals. |
| Explore another question | Ask for a count, sum, average, minimum, maximum or grouped ranking. Sales, profit, inventory and customer templates, charts and a SQL explorer also work on the selected sheet. |
| Share the result | Read the Chinese explanation above the figures and export the same text with the underlying tables and calculation evidence. |

## Run locally

From a copy of the repository, use Python 3.11 to create an environment. These commands are for macOS or Linux.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python launch.py --open
```

The launcher opens the dashboard at `http://127.0.0.1:8513/` on your machine. The synthetic workbook is selected at startup. Choose **本地规则** (local rules) in the sales review to try questions without installing a model, or use the manual period and product selectors. In **数据问答 · Ask**, choose **Local rules** and try “Total revenue by category”.

### Optional on-device AI

With Qwen2.5-7B-Instruct installed locally, the model interprets supported questions. DuckDB computes the figures. In the sales review, the model also selects which verified findings to highlight. General query explanations are composed from the computed result.

On an Apple Silicon Mac, place the extracted llama.cpp b12563 distribution with its executable at `.runtime/llama-b12563/llama-server`. Place both Qwen2.5-7B-Instruct **Q4_K_M** GGUF shards in `.runtime/` under their original filenames. Run the launcher again and select **本机 AI** in the sales review. It uses the local model endpoint on port 18089. [Official download sources, file hashes and licenses](docs/SOURCES.md) · [Launcher](launch.py)

## Scope and verification

Sales review uses a single worksheet with date, sales, gross profit and product or category fields. Missing months are flagged. If an entire comparison period is absent, the year-over-year change is left blank. Contribution figures identify where the change occurred. Explaining the effect of a promotion or stockout would require additional evidence.

The recorded run passed **142 automated tests** on the prepared Mac, plus a live check of four sales-review questions and one general category question using the local model. Fresh installation on other machines and public multi-user deployment have not been verified. Run the regression suite from the activated environment with `python -m pytest -q`. [Tests](tests/) · [Acceptance results](docs/ACCEPTANCE.md) · [Sales comparison implementation](insightflow/period_analysis.py)

The repository retains the upstream MIT notice for adapted type inference code. Attribution, dependency origins and separate model terms are documented in the project. [License](LICENSE) · [Sources and contributions](docs/SOURCES.md)

# Setup & Run — 6 steps, nothing else

---

## 1. Join the HuggingFace organization

Click the link below and accept the invite:

**→ <a href="https://huggingface.co/organizations/OCR-Data/share/MelLKBnsWnlzOIrDuwfdsUaxghgEQsmEdr" target="_blank">https://huggingface.co/organizations/OCR-Data/share/MelLKBnsWnlzOIrDuwfdsUaxghgEQsmEdr</a>**

> You need to be a member to push data to the shared dataset repo.

---

## 2. Clone the repo

```bash
git clone https://github.com/zetatiabdelhakim/OCR_Data.git
cd OCR_DATA\make_data\template_based_ocr_dataset_gen
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 4. Create your `.env` file

Copy the example file and fill in your token:

```bash
cp .env.example .env
```

Then open `.env` and replace the placeholder with your real HuggingFace token:

```
HF_TOKEN=hf_your_real_token_here
```
> Get your token here → <a href="https://huggingface.co/settings/tokens" target="_blank">https://huggingface.co/settings/tokens</a>  
> It needs **write** permission.
>> **Important:** Make sure to add the organization under **"Applied to:"** and select the **"write"** setting when creating the token.
---

## 5. Set your name in `config.yaml`

Open `config.yaml` and change **only this one line**:

```yaml
user_name: "your_name"   # ← put your name/handle here
```

**Do not change anything else.**

---

## 6. Run

```bash
python generate.py
```

That's it. The script handles everything automatically — batching, uploading to HuggingFace, and tracking your progress.

---

## ⚠️ Check your free disk space first

Generated data is packed into `.tar` shards and held locally until enough has
accumulated to be worth pushing (`push_threshold_gb`, default **50 GB**).
Because generation keeps running during a push, you hold roughly **two** of
those batches at once:

```
free space needed  ≈  (2 × push_threshold_gb) + 5 GB   ≈  105 GB at the default
```

If you don't have that, open `config.yaml` and either lower
`push_threshold_gb` (e.g. `25`) or set `pipeline_upload: false` — that halves
the requirement, at the cost of pausing generation during each push. Lower
`min_free_disk_gb` to match, or the script will refuse to start.

---

## ⚠️ Things you must NOT touch

| What | Why |
|---|---|
| `repo_id` in `config.yaml` | Shared team dataset — must be the same for everyone |
| `global_limit` | Controls when the whole team stops |
| `chunk_limit` | Sets the shard size (9990 ≈ 1.2 GB per shard) |
| `.env` | Never commit this file — it's in `.gitignore` |

---

## Where does the output go?

- If `destination: "hf"` (default) → packed into shards, uploaded to
  HuggingFace, **verified against the repo**, and only then deleted locally.
- If `destination: "lcl"` → shards land in `./dataset_local_output/`.

Local data is never deleted until the Hub confirms it actually has it. If a
push fails or you kill the run mid-transfer, the batch stays in `./work/` and
the next run finishes it — nothing is lost and there's no manual cleanup.

You don't need to do anything manually. Just let it run. It may be slow
starting, but all will be good once the resources are loaded.

If you stop it with Ctrl+C, anything already packed stays in `./work/outbox/`
and goes out with the next run's first push.

Thank you for following!

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

## ⚠️ Things you must NOT touch

| What | Why |
|---|---|
| `repo_id` in `config.yaml` | Shared team dataset — must be the same for everyone |
| `global_limit` | Controls when the whole team stops |
| `chunk_limit` | Controls upload batch size |
| `.env` | Never commit this file — it's in `.gitignore` |

---

## Where does the output go?

- If `destination: "hf"` (default) → uploaded automatically to HuggingFace, then deleted locally.
- If `destination: "lcl"` → saved to `./dataset_local_output/` on your machine.

You don't need to do anything manually. Just let it run. It may be slow starting, but all will be good at the time all resources are loaded.

Thank you for following!

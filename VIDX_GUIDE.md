# VIDX — Complete Usage Guide for KFI New Testament Project

> [!IMPORTANT]
> **Your project:** KFI New Testament (Kurumba Kannada Audio Bible)  
> **YAML file:** `D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml`  
> **Tool folder:** `D:\Seffin\vidx`

---

## 🖥️ STEP 0 — What to Install on Your Laptop (First Time Only)

Install these **4 things** in order:

### 1. Python 3.10+ (required)
- Download from: https://www.python.org/downloads/
- During install, **check ✅ "Add Python to PATH"** before clicking Install
- Verify: open PowerShell and type:
  ```powershell
  python --version
  ```
  Should print `Python 3.10.x` or higher.

### 2. FFmpeg (required — the video rendering engine)
- Download "Windows builds" from: https://ffmpeg.org/download.html  
  (Use the **BtbN** or **gyan.dev** build — get the "full" version)
- Extract the ZIP, copy the `bin` folder path (e.g., `C:\ffmpeg\bin`)
- Add it to your Windows **PATH**:
  1. Search "Environment Variables" in Start menu
  2. Under System Variables → **Path** → Edit → New → paste `C:\ffmpeg\bin`
- Verify:
  ```powershell
  ffmpeg -version
  ```

### 3. Install VIDX (required)
Open PowerShell inside `D:\Seffin\vidx`:
```powershell
cd D:\Seffin\vidx
pip install -e .
```
Verify:
```powershell
vidx --help
```

### 4. Install YouTube Upload Extra (required for YouTube publishing)
```powershell
pip install -e ".[youtube]"
```
Verify:
```powershell
python -c "import google.oauth2, googleapiclient; print('youtube extra OK')"
```

### 5. Fonts (required for Kannada/Tamil text)
Make sure these fonts are installed on Windows:
- **Mukta Malar Medium** (used in your YAML)
- **Mukta Malar SemiBold** (used for headings)
- **Tiro Tamil** (used for overlay title)
- **Impact** (used for watermark text)

To install: right-click a `.ttf`/`.otf` font file → **Install for all users**

---

## ▶️ STEP 1 — How to Run Your YAML File (Testing & Production)

Open PowerShell and `cd` to the **vidx project folder** (not the YAML folder):

```powershell
cd D:\Seffin\vidx
```

### 🧪 Quick Test (first 15 seconds of each chapter — to check styling)
```powershell
vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" -t 15
```
> Use this first! It renders only 15 seconds of each chapter so you can check fonts, colors, watermark position before committing hours of rendering time.

### 🚀 Full Production Render (all NT chapters)
```powershell
vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" -w 4
```

### ⚡ Full Render with GPU Acceleration (NVIDIA/Intel GPU — much faster)
```powershell
vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" --gpu -y -w 4
```
- `--gpu` → uses NVIDIA NVENC or Intel QSV (3–10× faster)
- `-y` → auto-confirms the 4K→1080p background downscale prompt
- `-w 4` → renders 4 chapters simultaneously (use `-w 2` on slower machines)

### 📄 Subtitles Only (no video rendering — fast)
```powershell
vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" --generate-only --format both
```

---

## 🎬 STEP 2 — Adding Intro Video & Outro (Outdraw)

VIDX natively supports both **pre-recorded video bumpers** (`intro_video` / `outro_video`) and **audio bumpers** (`intro_audio` / `outro_audio`).

Add this block to your `D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml` (after the `audio:` block):

### For Pre-recorded Video Files (.mp4):
```yaml
bumpers:
  intro_video: "src/kfi/assets/intro.mp4"       # Your intro video (plays before scripture video)
  outro_video: "src/kfi/assets/outro.mp4"       # Your outro / outdraw video (plays after scripture)
```

### For Audio-only Jingles (.mp3):
```yaml
bumpers:
  intro_audio: "src/kfi/assets/intro.mp3"       # Audio played over opening background
  outro_audio: "src/kfi/assets/outro.mp3"       # Audio played after narration ends
```

> [!NOTE]
> - VIDX **automatically shifts all subtitle timestamps** and **YouTube section chapter markers** by the exact intro duration — scripture sync stays 100% frame-accurate!
> - When using `intro_video` / `outro_video`, VIDX automatically normalises all clips to the project's target resolution and framerate, then stitches them using FFmpeg concat demuxer.

**For a title card image** (still frame shown before scripture begins):

```yaml
video:
  title_image: "src/kfi/assets/title_card.jpg"   # Still image shown at start
  title_duration: 4.0                             # Show for 4 seconds

bumpers:
  intro_audio: "src/kfi/assets/intro.mp3"
  outro_audio: "src/kfi/assets/outro.mp3"
  outro_image: "src/kfi/assets/end_card.jpg"     # Image shown during outro
```

---

## 📺 STEP 3 — YouTube Upload Guide

### Method A: Automated Upload (Recommended)

#### One-time Google Cloud Setup:

1. Go to https://console.cloud.google.com/ → **New Project** → name: `VIDX KFI Uploader`
2. **APIs & Services → Library** → search `YouTube Data API v3` → **Enable**
3. **APIs & Services → OAuth consent screen**:
   - Choose **External** → Create
   - App name: `VIDX Uploader`
   - **⚠️ Add Test Users:** Click **+ ADD USERS** → add your YouTube account email(s)
4. **APIs & Services → Credentials**:
   - `+ CREATE CREDENTIALS` → `OAuth client ID` → **Desktop app**
   - Click **DOWNLOAD JSON**
5. On your PC:
   - Create folder: `C:\Users\Kalaivani\.vidx\`
   - Rename and copy the JSON file there as: `client_secrets.json`

#### Run the Upload:
```powershell
vidx --manifest "output\kfi_nt\YouVersion 01\publish_manifest.json"
```
- Browser opens → sign in → select your **ministry/brand YouTube channel** (not personal)
- Google warning "unverified app" → click **Advanced → Go to VIDX Uploader (unsafe) → Allow**
- Upload starts automatically. VIDX uploads ~5–6 videos/day (Google's limit)
- **Next day:** run the exact same command — it resumes where it stopped

#### To switch YouTube channel (if you picked the wrong one):
```powershell
Remove-Item "output\kfi_nt\YouVersion 01\youtube_token.json"
vidx --manifest "output\kfi_nt\YouVersion 01\publish_manifest.json"
```

---

### Method B: Manual Drag-and-Drop Upload (No Google setup needed)

After rendering, look inside your output folder for:
```
output\kfi_nt\YouVersion 01\YouTube_Upload_Package\
    Matthew_Chapter_01\
        Matthew_Chapter_01.mp4
        title_card.jpg
        metadata.txt       ← copy-paste title, description, tags from here
    Matthew_Chapter_02\
        ...
```
1. Open https://studio.youtube.com/ → **Create → Upload Videos**
2. Drag the `.mp4` file into browser
3. Copy-paste title & description from `metadata.txt`
4. Upload `title_card.jpg` as thumbnail
5. Set playlist → Publish

---

## 📑 STEP 4 — YouTube Chapters & Sub-chapters in Description

VIDX **automatically generates YouTube chapter timestamps** from the `\s` section headings in your USFM files. Add `{chapters}` to your description template in the YAML:

```yaml
publishing:
  platform: "youtube"
  enabled: true
  privacy_status: "unlisted"
  playlist_name: "KFI New Testament — Kurumba Kannada Audio Bible"
  intro_label: "{h} {chapter}"
  conclusion_label: "{h} {chapter} முடிவு"
  title_template: "{h} {chapter:02d} — Kurumba Kannada Audio Bible"
  description_template: |
    {h} Chapter {chapter} — Kurumba Kannada Audio Bible
    
    📖 Scripture Chapters:
    {chapters}
    
    #KFI #KurumbaKannada #AudioBible #Scripture
  tags:
    - "Kurumba Kannada"
    - "Audio Bible"
    - "KFI"
    - "{h}"
    - "Scripture"
```

The `{chapters}` placeholder automatically generates YouTube chapter timestamps like:
```
0:00 Introduction
1:23 Section Heading 1 (1:1-8)
4:45 Section Heading 2 (1:9-15)
```

> [!IMPORTANT]
> YouTube **requires** for chapters to show:
> - First chapter must start at `0:00`
> - At least **3 chapter markers**
> - Each chapter must be **at least 10 seconds long**
>
> VIDX handles all these rules automatically. Verify chapters on the first upload before uploading all chapters!

### Add `publishing:` block to your YAML

Open `D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml` and add this **after the `overlay:` block**:

```yaml
publishing:
  platform: "youtube"
  enabled: true
  generate_offline_package: true
  privacy_status: "unlisted"
  category_id: "27"
  playlist_name: "KFI New Testament — Kurumba Kannada Audio Bible"
  intro_label: "{h} {chapter}"
  conclusion_label: "{h} {chapter} முடிவு"
  title_template: "{h} {chapter:02d} — Kurumba Kannada Audio Bible"
  description_template: |
    {h} Chapter {chapter} | Kurumba Kannada Audio Bible

    📖 Section Timestamps:
    {chapters}

    © KFI | Kurumba Kannada Christian Network
    #KurumbaKannada #AudioBible #KFI #Scripture
  tags:
    - "Kurumba Kannada"
    - "Audio Bible"
    - "KFI"
    - "{h}"
    - "Chapter {chapter}"
    - "Scripture"
    - "New Testament"
```

Also add language info to the `project:` block:
```yaml
project:
  name: "KFI New Testament — Kurumba Kannada Audio Bible"
  language: "Kurumba Kannada"
  text_copyright: "© KFI"
  audio_copyright: "© Kurumba Kannada Christian Network"
  # ... existing keys ...
```

---

## 📋 Quick Command Reference

| Task | Command |
|------|---------|
| Test render (15s each) | `vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" -t 15` |
| Full render (CPU) | `vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" -w 4` |
| Full render (GPU) | `vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" --gpu -y -w 4` |
| Subtitles only | `vidx -c "D:\Seffin\KK\kk_yaml\kfi_nt_full.yaml" --generate-only --format both` |
| Upload to YouTube | `vidx --manifest "output\kfi_nt\YouVersion 01\publish_manifest.json"` |
| Resume upload next day | Same command as above — VIDX resumes automatically |
| Switch YouTube channel | Delete `youtube_token.json`, then re-run upload command |

---

## ✅ Current Status: Installed & Production-Ready (v0.4.7)

Environment verified:
- ✔ Python 3.15 installed
- ✔ FFmpeg installed and in PATH
- ✔ `vidx` CLI & standalone executable `vidx.exe` v0.4.7 ready
- ✔ Video Bumpers (`intro_video`, `outro_video`, `end_screen_video`) fully operational
- ✔ Subheading markers with timestamps (`{chapters}`) active for YouTube descriptions & scrubber navigation


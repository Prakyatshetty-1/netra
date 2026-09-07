# NETRA Prototype — 100% Free Hosting Guide 🚀

This guide explains how to host the complete **NETRA Evidence Analysis & Dashboard Prototype** for **100% FREE**, including cases, the Cytoscape graph canvas, YOLOv8 CCTV object detection, and document OCR.

---

## 💡 Quick Fix for Hugging Face "Docker is Paid 🔒"

In Hugging Face Spaces, the **Docker SDK** now requires a paid subscription or credit card verification. 

**However, the "Gradio" SDK is 100% FREE, requires NO credit card, and gives you 16 GB RAM + 2 vCPUs!**

We have configured `app.py` in your project so that selecting **Gradio -> Blank** runs your entire React + FastAPI prototype on Hugging Face for free!

---

## 🌟 Method 1: Hugging Face Spaces with Gradio SDK (100% Free, 16 GB RAM)

### Why this works:
Gradio is built directly on top of FastAPI and Starlette. Our [app.py](file:///home/prakyatshetty/Documents/sihpro/app.py) mounts your full FastAPI application and serves your pre-compiled React frontend (`frontend/dist`) directly on root `/`.

### Step-by-Step Instructions:

1. Go to **[huggingface.co/new-space](https://huggingface.co/new-space)** (as shown in your screenshot).
2. Fill in the Space details:
   - **Owner**: `Prakyat`
   - **Space name**: `netra-prototype`
   - **Short description**: `NETRA Crime Evidence & CCTV Analysis Dashboard`
   - **License**: `mit` or `apache-2.0`
3. Under **Select the Space SDK**:
   - Choose **Gradio** 🟧 *(Free)*
   - Choose Gradio template: **Blank** *(Free)*
4. Under **Space hardware**:
   - Keep default: **CPU basic · 2 vCPU · 16 GB · FREE**
5. Set Visibility: **Public**
6. Click **Create Space**.

---

### Push Your Code to Hugging Face:

In your local terminal, add the Hugging Face remote and push your code:

```bash
# 1. Add Hugging Face Space as remote
git remote add space https://huggingface.co/spaces/Prakyat/netra-prototype

# 2. Push your branch to Hugging Face main
git push space prakyat:main
```

> **Note on Authentication**: If prompted for a password during `git push`, use your **Hugging Face Access Token** (generate a free `Write` token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)).

Once pushed, Hugging Face will install `requirements.txt`, run `app.py`, and your full dashboard will be live at:
`https://prakyat-netra-prototype.hf.space`

---

### Add Optional Gemini API Key on Hugging Face:
To enable Google Gemini 2.5 Flash Vision OCR on uploaded handwritten documents:
1. In your Space, click **Settings** (top right).
2. Scroll to **Variables and secrets**.
3. Click **New secret**:
   - Name: `GEMINI_API_KEY`
   - Value: *(your Gemini API key from [aistudio.google.com](https://aistudio.google.com/))*
4. Click **Save**.

---

## ⚡ Method 2: Cloudflare Tunnel (Instant Zero-Cost Hackathon / SIH Live Demo)

If you are presenting to judges at **Smart India Hackathon (SIH)** or evaluating before a jury, running locally and sharing an instant public HTTPS link is the fastest and most dependable method (it runs at full speed with your local GPU/CPU with 0 cloud limitations):

1. **Start the backend server**:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

2. **Open a free Cloudflare Tunnel** in a second terminal (no signup, no credit card):
   ```bash
   # Quick install (if not already installed):
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb

   # Launch public URL:
   cloudflared tunnel --url http://localhost:8000
   ```
   *Cloudflare will print a secure URL like `https://xxxx.trycloudflare.com` that you can share with judges to test directly on their phones or laptops.*

*(Alternative using ngrok)*:
```bash
ngrok http 8000
```

---

## 🌐 Method 3: Render.com (Free Native Python Web Service)

Render allows hosting Python FastAPI web apps directly from GitHub without Docker:

1. Go to **[render.com](https://render.com/)** and sign up for free.
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository (`sihpro`).
4. Select:
   - **Runtime**: `Python 3`
   - **Branch**: `prakyat`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: Free (512 MB)
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: `<your-key>`
6. Click **Deploy Web Service**.

---

## 📋 Pre-Deployment Test Command

Before pushing, verify everything passes locally:

```bash
# Verify all integration and unit tests pass
pytest
```
*(All 6 tests should report green passing status)*

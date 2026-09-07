# NETRA Prototype — 100% Free Hosting Guide 🚀

This guide provides proven, genuinely **100% FREE** methods to host and share the complete **NETRA Evidence Analysis & Dashboard Prototype** with judges, jury members, or your team.

---

## ⚠️ Important Update on Hugging Face Spaces

As shown on the Hugging Face Space creation screen:
- **Static** (pure HTML/JS only) is free.
- **Gradio** 🔒 **Paid** (now requires a PRO subscription).
- **Docker** 🔒 **Paid** (now requires a PRO subscription or credit card).

Because NETRA requires a Python backend (FastAPI, YOLOv8 object detection, OpenCV, and SQLite), it cannot run under Hugging Face's Static tier. Below are the **best 100% free, working alternatives**.

---

## 🌟 Method 1: Cloudflare Quick Tunnel (Best for SIH & Live Demos)

**Why this is the #1 recommended choice for hackathons & jury presentations:**
- **100% FREE** with **NO account, NO sign-up, and NO credit card required**.
- **Instant global HTTPS URL** (`https://xxxx.trycloudflare.com`) with Cloudflare SSL & DDoS protection.
- Runs with your local machine's full CPU/GPU speed — **zero cold-start delay, no cloud memory limits, and no 15-minute C++ build waits**.
- **`cloudflared` is already installed and ready on your system!**

### Step-by-Step Instructions:

1. **Terminal 1 — Start the application server**:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
   *(This serves the full React frontend and FastAPI backend at `http://localhost:8000`)*

2. **Terminal 2 — Launch the public Cloudflare tunnel**:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

3. **Share the Link**:
   Look at the terminal output for the generated URL:
   ```text
   +--------------------------------------------------------------------------------------------+
   |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
   |  https://random-words-here.trycloudflare.com                                              |
   +--------------------------------------------------------------------------------------------+
   ```
   Open that `https://...trycloudflare.com` link on your phone, laptop, or share it with the judges!

---

## ⚡ Method 2: Instant SSH Tunnel (Zero Install, Built-in Linux SSH)

If you don't want to run any CLI tool, Linux has built-in SSH tunneling services:

1. **Start the backend server**:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

2. **In a second terminal, run `localhost.run`**:
   ```bash
   ssh -R 80:localhost:8000 nokey@localhost.run
   ```
   *Prints a live `https://xxxx.lhr.life` public HTTPS link.*

3. *(Alternative using Pinggy)*:
   ```bash
   ssh -p 443 -R0:localhost:8000 a.pinggy.io
   ```

4. *(Alternative using npx localtunnel)*:
   ```bash
   npx -y localtunnel --port 8000
   ```

---

## 🌐 Method 3: Render.com (Free 24/7 Cloud Hosting)

If you want a standing 24/7 cloud server that stays online even when your laptop is closed:

1. Go to **[render.com](https://render.com/)** and sign up for free (using GitHub).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository: `Prakyatshetty-1/netra` (already pushed and up to date!).
4. Configure the service:
   - **Runtime**: `Python 3`
   - **Branch**: `main`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: `Free`
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: *(your Gemini key from [aistudio.google.com](https://aistudio.google.com/))*
6. Click **Deploy Web Service**.
   Render will deploy your app at: `https://netra-xxxx.onrender.com`.

---

## 📋 Quick Local Verification

Before presenting or deploying, verify all backend routes and integration tests pass:

```bash
pytest
```
*(All 6 integration and crop tests should pass with 100% green status)*

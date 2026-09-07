# NETRA Prototype — Free Hosting Guide 🚀

This guide explains how to deploy and host the **NETRA Evidence-Centric Crime Analysis & Ingestion Dashboard** for **100% FREE** with full functionality (FastAPI backend, SQLite database, Cytoscape graph canvas, YOLOv8 CCTV object detection, Gemini/TrOCR document OCR, and Photo crop relationship extraction).

---

## 📊 Free Hosting Options Comparison

| Platform | Best For | Specs (Free Tier) | RAM / ML Capability | Setup Effort |
| :--- | :--- | :--- | :--- | :--- |
| **1. Hugging Face Spaces (Docker)** ⭐ *(Recommended)* | Full ML Prototype (YOLO + PyTorch + SQLite) | **16 GB RAM**, 2 vCPUs, 50 GB Disk, Unlimited Uptime | 🟢 **Best** (Won't crash on heavy PyTorch / YOLO models) | Low (Push to Git repo) |
| **2. Cloudflare Tunnel / ngrok** ⭐ *(Best for Hackathons)* | Live Jury / SIH Demo from Laptop | Uses your laptop hardware & GPU | 🟢 **Zero cloud limits** (Fastest inference) | 2 minutes (1 command) |
| **3. Render.com + Vercel** | Traditional Web Stack | 512 MB RAM (Render) + Unlimited CDN (Vercel) | 🟡 Good with Gemini API (PyTorch locally may hit 512MB limit) | Medium |
| **4. Koyeb** | Containerized Microservices | 512 MB RAM, 0.1 vCPU, Global Edge | 🟡 Good with lightweight models (`yolov8n.pt`) | Low (Connects to GitHub) |

---

## 🌟 Option 1: Hugging Face Spaces (Recommended for NETRA)

**Why this is the best free option for NETRA:**
Python ML libraries (`ultralytics`, `torch`, `opencv`, `transformers`) require significant memory. Most free cloud providers (Render, Railway free tier) cap RAM at 512MB, which causes `Out Of Memory (OOM)` errors when loading YOLO or PyTorch.
**Hugging Face Spaces provides 16 GB of RAM, 2 vCPUs, and 50 GB storage completely free forever!**

### Step-by-Step Deployment:

1. **Create an account** on [huggingface.co](https://huggingface.co/) (if you haven't already).
2. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
3. Configure your Space:
   - **Space name**: `netra-prototype`
   - **License**: `mit` or `apache-2.0`
   - **Space SDK**: Select **Docker** 🐳
   - **Docker template**: Select **Blank**
   - **Visibility**: **Public**
   - Click **Create Space**.
4. In your local terminal, add the Hugging Face space as a git remote:
   ```bash
   git remote add space https://huggingface.co/spaces/<YOUR_USERNAME>/netra-prototype
   ```
5. Add the `Dockerfile` provided below to your project root.
6. Commit and push:
   ```bash
   git add Dockerfile
   git commit -m "Add Dockerfile for Hugging Face Spaces deployment"
   git push space prakyat:main
   ```
7. Hugging Face will automatically build the container and provide you with a public HTTPS link (e.g. `https://<YOUR_USERNAME>-netra-prototype.hf.space`)!
8. **Add Secret for Gemini API**:
   - Go to your Space **Settings** -> **Variables and secrets**.
   - Add a Secret: `GEMINI_API_KEY` with your Google Gemini API key.

---

## ⚡ Option 2: Cloudflare Tunnel (Instant Zero-Cost Hackathon & Jury Demo)

If you are presenting at **Smart India Hackathon (SIH)** or evaluating before a jury, running the models directly on your laptop with a **Cloudflare Tunnel** is the most reliable approach:
- **No cloud memory limits**: YOLO and Gemini run at full speed utilizing your local CPU/GPU.
- **100% Free**: No credit card, no account required.
- **Gives you a public HTTPS URL** that judges can open on their mobile phones or laptops to test the prototype live.

### How to Run:

1. Start your NETRA servers locally:
   ```bash
   # Terminal 1: Backend
   source .venv/bin/activate
   uvicorn backend.main:app --host 0.0.0.0 --port 8000

   # Terminal 2: Frontend
   cd frontend
   npm run build
   # (Or run dev server: npm run dev -- --host 0.0.0.0 --port 5173)
   ```

2. Expose with Cloudflare Tunnel (no signup needed):
   ```bash
   # Install cloudflared (Linux):
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb

   # Expose your app:
   cloudflared tunnel --url http://localhost:8000
   ```
   *Cloudflare will print a public URL like `https://random-words.trycloudflare.com` that connects directly to your app.*

*(Alternative using ngrok)*:
```bash
ngrok http 8000
```

---

## 🌐 Option 3: Render (Backend) + Vercel (Frontend)

If you prefer hosting frontend and backend on separate specialized free platforms:

### Part A: Deploy Backend on Render.com
1. Sign up for free at [render.com](https://render.com/).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository (`sihpro`).
4. Settings:
   - **Name**: `netra-backend`
   - **Environment**: `Python 3`
   - **Branch**: `prakyat`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Plan**: Free (512 MB)
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: `<your_gemini_api_key>`
6. Click **Create Web Service**. Note your Render URL (e.g. `https://netra-backend.onrender.com`).

> **Tip for Render Free Tier**: Because Render free tier has 512 MB RAM, stick to `yolov8n.pt` (nano) and Gemini Vision AI for OCR.

### Part B: Deploy Frontend on Vercel
1. Sign up for free at [vercel.com](https://vercel.com/).
2. Click **Add New** -> **Project** -> Import your repository.
3. Configure Project:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add Environment Variable:
   - `VITE_API_BASE_URL`: `https://netra-backend.onrender.com` (your Render backend URL)
5. Click **Deploy**. Vercel will deploy your frontend to a global edge CDN in under 1 minute!

---

## 🐳 Universal Dockerfile (For Hugging Face, Koyeb, Render Docker)

To run NETRA as a single self-contained application, use this production-ready Dockerfile:

```dockerfile
# -----------------------------------------------------------------------------
# Multi-stage Dockerfile for NETRA Prototype
# Stage 1: Build Frontend Assets
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Python Backend & Static Server
# -----------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

# Install system dependencies for OpenCV and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend, database, model weights, and sample assets
COPY backend/ ./backend/
COPY uploads/ ./uploads/
COPY netra_sim.db .
COPY audit_log.jsonl .
COPY *.pt ./

# Copy built frontend assets from Stage 1 into frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY --from=frontend-builder /app/frontend/package.json ./frontend/

# Create necessary upload/crop runtime directories
RUN mkdir -p frontend/crops frontend/annotated uploads/cctv uploads/documents

EXPOSE 7860

# Run uvicorn on the configured port
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
```

---

## 🔑 Environment Variables & API Keys

NETRA works out-of-the-box using local models, but for the highest accuracy OCR on noisy handwritten FIR documents, you can supply a Gemini API key:

| Variable | Required | Description |
| :--- | :--- | :--- |
| `PORT` | Optional (default `8000` or `7860`) | Server listening port (set automatically by host) |
| `GEMINI_API_KEY` | Optional | Google Gemini 2.5 Flash Vision key for handwritten FIR text extraction |
| `VITE_API_BASE_URL` | Optional | Backend URL (only needed if frontend is deployed separately on Vercel/Netlify) |

*You can get a free Gemini API key with no credit card at [aistudio.google.com](https://aistudio.google.com).*

---

## 🛠️ Pre-Deployment Verification Checklist

Before deploying, run these two commands in your terminal to verify everything builds and passes:

1. **Test backend endpoints and integration**:
   ```bash
   pytest
   ```
   *(Should show all 6 tests passing)*

2. **Test frontend production build**:
   ```bash
   cd frontend && npm run build
   ```
   *(Should complete with 0 build errors)*

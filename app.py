"""Entrypoint for Hugging Face Spaces (Gradio SDK) or direct Uvicorn launch."""

import os
from pathlib import Path
from backend.main import app

# In Hugging Face Spaces with Gradio SDK, gradio is pre-installed.
try:
    import gradio as gr

    with gr.Blocks(title="NETRA Dashboard") as demo:
        gr.HTML(
            """
            <div style="font-family: system-ui, sans-serif; padding: 30px; text-align: center; background: #0f172a; color: #fff; border-radius: 12px; margin: 20px auto; max-width: 600px;">
              <h2 style="margin-bottom: 8px;">NETRA Evidence Analysis Dashboard</h2>
              <p style="color: #94a3b8; font-size: 14px;">The full React Investigator Dashboard is live and running.</p>
              <a href="/" target="_top" style="display: inline-block; margin-top: 16px; padding: 10px 22px; background: #2563eb; color: #fff; border-radius: 8px; text-decoration: none; font-weight: 600;">
                Open NETRA Dashboard →
              </a>
            </div>
            """
        )

    # Mount Gradio at /gradio so root / remains the full NETRA React Dashboard
    app = gr.mount_gradio_app(app, demo, path="/gradio")
except ImportError:
    pass

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)

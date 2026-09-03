"""Entrypoint for Hugging Face Spaces OR Render (or any host that sets $PORT)."""
import os
from ui import demo

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, ssr_mode=False)

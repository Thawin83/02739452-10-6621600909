"""Entry point: defines the sidebar navigation (Thai page names)."""
import sys
from pathlib import Path

import streamlit as st

# Pages live in views/ but import the shared ui/db modules from this folder.
sys.path.insert(0, str(Path(__file__).parent))

st.navigation([
    st.Page("views/overview.py", title="ภาพรวมลีก", icon="⚽", default=True),
    st.Page("views/pipeline_status.py", title="สถานะ Pipeline", icon="🛠️", url_path="pipeline"),
]).run()

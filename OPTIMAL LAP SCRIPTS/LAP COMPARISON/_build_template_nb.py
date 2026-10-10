"""Builds OPTIMAL_X_QUALI.ipynb from LAPCOMP.IPYNB: DB/API/UI code kept, baker swapped for the optimal-road one.
Re-run after editing LAPCOMP.IPYNB's UI:  python _build_template_nb.py"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
src_nb = json.load(open(os.path.join(HERE, "LAPCOMP.IPYNB"), encoding="utf-8"))
L = "".join(src_nb["cells"][0]["source"]).split("\n")
i_delta = next(i for i, l in enumerate(L) if "1. HIGH-FIDELITY DELTA ENGINE" in l) - 1
i_ui = next(i for i, l in enumerate(L) if "3. INTERACTIVE WIDGET UI PIPELINE" in l) - 1
head = "\n".join(L[:i_delta])    # imports, DB connection, API preflight (unchanged)
ui = "\n".join(L[i_ui:])         # widget UI (unchanged except the edits below)
mid = open(os.path.join(HERE, "_template_baker.py"), encoding="utf-8").read()

edits = [
    ("w_zoom = widgets.FloatSlider(value=3.0, min=0.5, max=20.0, step=0.5, description='Zoom Level:')",
     "w_zoom = widgets.FloatSlider(value=1.0, min=0.25, max=3.0, step=0.05, description='Zoom x:')  # x the optimal-lap zoom"),
    ('widgets.HTML("<h2>🏎️ F1 Global Cross-Year Automation</h2>")',
     'widgets.HTML("<h2>🏎️ OPTIMAL x QUALI — Lap Comparison on the Optimal-Lap Road</h2>")'),
    ("btn_top3 = widgets.Button(description=\"AUTO TOP 3\", button_style='info')",
     "btn_top2 = widgets.Button(description=\"AUTO TOP 2\", button_style='warning')\n"
     "btn_top3 = widgets.Button(description=\"AUTO TOP 3\", button_style='info')"),
    ("btn_top3.on_click(lambda b: on_auto_generate(3))",
     "btn_top2.on_click(lambda b: on_auto_generate(2))\nbtn_top3.on_click(lambda b: on_auto_generate(3))"),
    ("buttons_box = widgets.HBox([btn_gen, btn_top3, btn_top5])",
     "buttons_box = widgets.HBox([btn_gen, btn_top2, btn_top3, btn_top5])"),
]
for a, b in edits:
    assert a in ui, a
    ui = ui.replace(a, b)
code = head + "\n" + mid + "\n" + ui
compile(code, "OPTIMAL_X_QUALI", "exec")
nb = {"cells": [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                 "source": [l + "\n" for l in code.split("\n")[:-1]] + [code.split("\n")[-1]]}],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
json.dump(nb, open(os.path.join(HERE, "OPTIMAL_X_QUALI.ipynb"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("OPTIMAL_X_QUALI.ipynb written,", len(code.split("\n")), "lines")

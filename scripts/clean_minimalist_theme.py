import os
import re

def clean_minimalist_theme():
    # 1. Clean production.html
    prod_path = os.path.join(os.path.dirname(__file__), "..", "static", "production.html")
    with open(prod_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Define clean minimalist CSS variables & global rules
    minimal_style = """  <style>
    :root {
      --bg:            #F7F6F2;   /* page background, warm off-white */
      --surface:       #FFFFFF;   /* cards, sidebar, top bar */
      --border:        #DEDBD2;   /* subtle borders */
      --text:          #1C2B2A;   /* high-contrast deep slate text */
      --text-muted:    #5B6B69;   /* muted labels */
      --accent:        #0F766E;   /* deep teal: primary button, active tab */
      --accent-soft:   #E3F3F0;   /* selected row, info chips */
      --accent-text:   #0B524C;   /* text on accent-soft */
      --warn-bg:       #FBE9C6;   /* subtle status warning */
      --warn-text:     #7A4A05;
      --danger-bg:     #FBE0DC;   /* subtle status danger */
      --danger-text:   #8F2A1D;

      --font-family:   -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    * {
      font-family: var(--font-family) !important;
      transition: all 150ms ease-in-out;
      box-sizing: border-box;
    }

    body {
      background-color: var(--bg) !important;
      color: var(--text) !important;
      font-size: 14px !important;
      font-weight: 400 !important;
      line-height: 1.5;
    }

    /* Font Weights Strictly 400 and 500 Only */
    h1, h2, h3, h4, h5, h6, b, strong, th,
    .font-bold, .font-semibold, .font-black, .font-extrabold, .font-medium {
      font-weight: 500 !important;
    }
    .font-normal, span, p, td, li, input, select, textarea {
      font-weight: 400 !important;
    }

    /* Strict Font Sizes: 12 / 14 / 16 / 24 / 32 */
    .text-xs, .text-\\[9px\\], .text-\\[9\\.5px\\], .text-\\[10px\\], .text-\\[10\\.5px\\], .text-\\[11px\\] {
      font-size: 12px !important;
    }
    .text-sm, .text-\\[13px\\] {
      font-size: 14px !important;
    }
    .text-base {
      font-size: 16px !important;
    }
    .text-lg, .text-xl, .text-2xl {
      font-size: 24px !important;
    }
    .text-3xl, .text-4xl, .text-5xl {
      font-size: 32px !important;
    }

    /* Clean Minimalist Surfaces */
    aside, header, nav, .bg-slate-900, .bg-slate-950, .bg-slate-900\\/90, .bg-slate-950\\/60,
    .bg-slate-950\\/40, .bg-slate-950\\/50, .bg-slate-950\\/70, .bg-slate-950\\/80, .bg-slate-900\\/80 {
      background-color: var(--surface) !important;
    }
    .bg-slate-800, .bg-slate-800\\/60, .bg-slate-800\\/40, .bg-slate-800\\/80, .bg-slate-850 {
      background-color: var(--bg) !important;
    }

    /* Clean Subtle Borders (No loud neon outlines) */
    .border-slate-800, .border-slate-700, .border-slate-800\\/80, .border-slate-700\\/60, .border-slate-700\\/50,
    .border-slate-900, .divide-slate-800, .divide-slate-800\\/60 {
      border-color: var(--border) !important;
    }

    /* Clean Contrast Text */
    .text-white, .text-slate-100, .text-slate-200, .text-slate-300, h1, h2, h3, h4, th {
      color: var(--text) !important;
    }
    .text-slate-400, .text-slate-500, .text-slate-600 {
      color: var(--text-muted) !important;
    }

    /* Neutral Icons (No rainbow clutter) */
    i.fa-solid, i.fa-regular, i.fa-brands {
      color: var(--text-muted);
    }
    .text-accent, i.text-accent {
      color: var(--accent) !important;
    }

    /* Accent: Deep Teal (Single Brand Colour) */
    .bg-indigo-600, .bg-indigo-500, .bg-teal-600, .bg-emerald-600, .hover\\:bg-indigo-500:hover,
    .hover\\:bg-teal-500:hover, .hover\\:bg-emerald-500:hover {
      background-color: var(--accent) !important;
      color: #FFFFFF !important;
    }
    .text-indigo-400, .text-indigo-300, .text-indigo-500, .text-teal-400, .text-teal-300, .text-emerald-400, .text-emerald-300 {
      color: var(--accent) !important;
    }
    .border-indigo-500, .border-indigo-600, .border-teal-500, .border-emerald-500 {
      border-color: var(--accent) !important;
    }
    .bg-indigo-950, .bg-indigo-950\\/40, .bg-indigo-950\\/30, .bg-teal-950, .bg-teal-950\\/40,
    .bg-indigo-500\\/10, .bg-indigo-500\\/20, .bg-teal-500\\/10, .bg-teal-500\\/20, .bg-emerald-500\\/10, .bg-emerald-500\\/20 {
      background-color: var(--accent-soft) !important;
      color: var(--accent-text) !important;
    }

    /* Subtle Status Colours: Warm Sand for Warnings, Muted Rose for Danger */
    .bg-amber-500\\/10, .bg-amber-500\\/20, .bg-amber-950, .bg-amber-950\\/60, .bg-amber-950\\/80 {
      background-color: var(--warn-bg) !important;
      color: var(--warn-text) !important;
      border-color: var(--warn-bg) !important;
    }
    .text-amber-400, .text-amber-300, .text-amber-500 {
      color: var(--warn-text) !important;
    }
    .bg-rose-500\\/10, .bg-rose-500\\/20, .bg-rose-950, .bg-rose-950\\/60, .bg-rose-950\\/80, .bg-rose-600 {
      background-color: var(--danger-bg) !important;
      color: var(--danger-text) !important;
      border-color: var(--danger-bg) !important;
    }
    .text-rose-400, .text-rose-300, .text-rose-500 {
      color: var(--danger-text) !important;
    }

    /* Button Hierarchy:
       Primary = solid teal (Send Token UPI)
       Secondary = white with border (AutoPay Mandate, File Hospicash)
       Tertiary = plain text (Clear Settlement)
    */
    .btn-primary, button.btn-primary {
      background-color: var(--accent) !important;
      color: #FFFFFF !important;
      font-weight: 500 !important;
      border: 1px solid var(--accent) !important;
      border-radius: 8px !important;
      padding: 6px 14px !important;
      cursor: pointer;
      box-shadow: none !important;
    }
    .btn-primary:hover {
      background-color: var(--accent-text) !important;
      border-color: var(--accent-text) !important;
    }
    .btn-secondary, button.btn-secondary {
      background-color: var(--surface) !important;
      color: var(--text) !important;
      border: 1px solid var(--border) !important;
      font-weight: 500 !important;
      border-radius: 8px !important;
      padding: 6px 14px !important;
      cursor: pointer;
      box-shadow: none !important;
    }
    .btn-secondary:hover {
      background-color: var(--bg) !important;
      border-color: var(--accent) !important;
    }
    .btn-tertiary, button.btn-tertiary {
      background: transparent !important;
      border: none !important;
      color: var(--text-muted) !important;
      font-weight: 500 !important;
      padding: 6px 10px !important;
      cursor: pointer;
    }
    .btn-tertiary:hover {
      color: var(--text) !important;
      text-decoration: underline;
    }

    /* Selected Row & Clean Hover States */
    tr.selected-row, tr[aria-selected="true"] {
      background-color: var(--accent-soft) !important;
      border-left: 3px solid var(--accent) !important;
    }
    tr:hover {
      background-color: var(--bg) !important;
    }

    /* Minimalist Waveform */
    @keyframes waveBar {
      0%, 100% { height: 4px; }
      50% { height: 18px; }
    }
    .wave-active .w-bar-1 { animation: waveBar 0.8s infinite 0.1s ease-in-out; }
    .wave-active .w-bar-2 { animation: waveBar 0.8s infinite 0.25s ease-in-out; }
    .wave-active .w-bar-3 { animation: waveBar 0.8s infinite 0.4s ease-in-out; }
    .wave-active .w-bar-4 { animation: waveBar 0.8s infinite 0.2s ease-in-out; }
    .wave-active .w-bar-5 { animation: waveBar 0.8s infinite 0.35s ease-in-out; }

    /* Custom Scrollbar */
    .custom-scroll::-webkit-scrollbar { width: 5px; height: 5px; }
    .custom-scroll::-webkit-scrollbar-track { background: var(--bg); }
    .custom-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
    .custom-scroll::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

    /* Strip all box shadows for flat, minimalist look */
    .shadow-lg, .shadow-xl, .shadow-2xl, .shadow-md {
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
    }

    /* Clean Chat Transcript Bubbles */
    .chat-bubble-agent {
      background-color: var(--surface) !important;
      border: 1px solid var(--border) !important;
      color: var(--text) !important;
      border-radius: 8px !important;
    }
    .chat-bubble-borrower {
      background-color: var(--bg) !important;
      border: 1px solid var(--border) !important;
      color: var(--text) !important;
      border-radius: 8px !important;
    }
  </style>"""

    # Replace <style> block
    s_idx = html.find("<style>")
    e_idx = html.find("</style>")
    if s_idx != -1 and e_idx != -1:
        html = html[:s_idx] + minimal_style + html[e_idx + len("</style>"):]

    # Remove all garish gradients like bg-gradient-to-r, bg-gradient-to-tr
    html = re.sub(r'bg-gradient-to-[a-z]+(\s+[a-z0-9\-]+){1,5}', '', html)

    # Clean up multi-colored buttons in scenario bar
    # Replace scenario pill colors with clean minimalist styles
    html = re.sub(r'bg-indigo-600\s+text-white\s+shadow-sm', 'bg-teal-700 text-white font-medium', html)
    html = re.sub(r'bg-slate-800\s+text-slate-300\s+hover:text-white\s+hover:bg-slate-700', 'bg-white text-slate-700 border border-slate-300 hover:border-teal-700', html)

    with open(prod_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Cleaned production.html with minimalist design!")

    # 2. Clean coach.html
    coach_path = os.path.join(os.path.dirname(__file__), "..", "static", "coach.html")
    with open(coach_path, "r", encoding="utf-8") as f:
        coach_html = f.read()

    cs_idx = coach_html.find("<style>")
    ce_idx = coach_html.find("</style>")
    if cs_idx != -1 and ce_idx != -1:
        coach_html = coach_html[:cs_idx] + minimal_style + coach_html[ce_idx + len("</style>"):]

    coach_html = re.sub(r'bg-gradient-to-[a-z]+(\s+[a-z0-9\-]+){1,5}', '', coach_html)
    with open(coach_path, "w", encoding="utf-8") as f:
        f.write(coach_html)
    print("Cleaned coach.html with minimalist design!")

if __name__ == "__main__":
    clean_minimalist_theme()

import os, re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

CSS_BLOCK = """<style id="step6-palette">
    :root {
      /* STEP 6 SPECIFIED PALETTE */
      --cream:   #FFF9F0;   /* page background */
      --card:    #FFFFFF;   /* panels */
      --line:    #F0E6D2;   /* borders */
      --ink:     #2B2438;   /* text */
      --muted:   #7A6F8A;   /* secondary text */
      --indigo:  #2A2F8F;   /* header, primary button, borrower chat bubble */
      --saffron: #F59E0B;   /* avatar, "Act" step, payment button */
      --teal:    #0F9D8A;   /* success, "Prove" step, passed-check chips (bg #DDF4F0, text #0A5F54) */
      --purple:  #8B5CF6;   /* "Understand" step (tint #EFE8FD) */
      --red:     #E2574C;   /* "Detect" step and failures (tint #FDE8E6) */

      /* Tints */
      --purple-tint: #EFE8FD;
      --red-tint:    #FDE8E6;
      --teal-tint:   #DDF4F0;
      --teal-text:   #0A5F54;

      /* Canonical aliases */
      --bg:            var(--cream);
      --surface:       var(--card);
      --border:        var(--line);
      --text:          var(--ink);
      --text-muted:    var(--muted);
      --accent:        var(--indigo);
      --accent-soft:   var(--purple-tint);
      --accent-text:   var(--indigo);
      --warn-bg:       #FEF3C7;
      --warn-text:     #92400E;
      --danger-bg:     var(--red-tint);
      --danger-text:   var(--red);

      --font-family:   -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    /* Flat colours only, no gradients or shadows */
    *, *::before, *::after {
      font-family: var(--font-family) !important;
      box-shadow: none !important;
      text-shadow: none !important;
    }

    body, html {
      background-color: var(--cream) !important;
      color: var(--ink) !important;
      font-size: 14px !important;
      font-weight: 400 !important;
      line-height: 1.5;
    }

    /* Fonts: one family, weights 400 and 500 only */
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
    .text-base, .text-\\[15px\\] {
      font-size: 16px !important;
    }
    .text-lg, .text-xl, .text-2xl {
      font-size: 24px !important;
    }
    .text-3xl, .text-4xl, .text-5xl {
      font-size: 32px !important;
    }

    /* Top Header: --indigo with white text */
    header, .app-header {
      background-color: var(--indigo) !important;
      border-bottom: 1px solid var(--line) !important;
    }
    header h2, header h3, header span, header div, header p {
      color: #FFFFFF !important;
    }
    header .text-slate-400, header .text-slate-500, header .text-slate-600 {
      color: rgba(255, 255, 255, 0.85) !important;
    }

    /* Page background: --cream */
    .bg-slate-950, .bg-slate-950\\/50, .bg-slate-950\\/60, .bg-slate-950\\/40, .bg-slate-950\\/80 {
      background-color: var(--cream) !important;
    }

    /* Panels & Cards: --card */
    aside, .bg-slate-900, .bg-slate-800, .bg-slate-800\\/60, .bg-slate-800\\/80, .bg-slate-900\\/60, .bg-slate-900\\/80, .panel-card {
      background-color: var(--card) !important;
    }

    /* Structural Borders: --line */
    .border-slate-800, .border-slate-700, .border-slate-800\\/80, .border-slate-800\\/60, .border-slate-900, .border-slate-600 {
      border-color: var(--line) !important;
    }

    /* Text: --ink (high contrast) */
    .text-white, .text-slate-100, .text-slate-200, .text-slate-300 {
      color: var(--ink) !important;
    }

    /* Secondary / Muted Text: --muted */
    .text-slate-400, .text-slate-500, .text-slate-600 {
      color: var(--muted) !important;
    }

    /* Avatar: --saffron */
    #custAvatar, .avatar-saffron {
      background-color: var(--saffron) !important;
      color: #FFFFFF !important;
    }

    /* Primary buttons: --indigo */
    .btn-primary, button.bg-indigo-600, button.bg-indigo-700, #audioControlBtn {
      background-color: var(--indigo) !important;
      color: #FFFFFF !important;
      border: none !important;
    }

    /* Payment & Act buttons: --saffron */
    .btn-payment, #btnSimulatePayment, #btnDisburseToken, button.bg-amber-500, button.bg-amber-600, #btnKhataMic {
      background-color: var(--saffron) !important;
      color: #FFFFFF !important;
      border: none !important;
    }

    /* Passed-check chips & "Prove" step: --teal, bg #DDF4F0, text #0A5F54 */
    .chip-passed, .bg-emerald-500\\/20, .bg-teal-500\\/20 {
      background-color: #DDF4F0 !important;
      color: #0A5F54 !important;
      border: 1px solid var(--teal) !important;
    }

    /* "Understand" step: --purple with tint #EFE8FD */
    .step-understand, .bg-purple-500\\/20, .bg-purple-950\\/40 {
      background-color: #EFE8FD !important;
      color: var(--purple) !important;
      border: 1px solid var(--purple) !important;
    }

    /* "Detect" step & failures: --red with tint #FDE8E6 */
    .step-detect, .bg-rose-500\\/20, .bg-red-500\\/20 {
      background-color: #FDE8E6 !important;
      color: var(--red) !important;
      border: 1px solid var(--red) !important;
    }

    /* Chat Bubbles: borrower chat bubble = --indigo */
    .bubble-borrower, .items-end .rounded-2xl {
      background-color: var(--indigo) !important;
      color: #FFFFFF !important;
      border: 1px solid var(--indigo) !important;
    }
    .bubble-borrower *, .items-end .rounded-2xl * {
      color: #FFFFFF !important;
    }

    /* Agent chat bubble: --card with --line border */
    .bubble-agent, .items-start .rounded-2xl {
      background-color: var(--card) !important;
      color: var(--ink) !important;
      border: 1px solid var(--line) !important;
    }
    .bubble-agent *, .items-start .rounded-2xl * {
      color: var(--ink) !important;
    }

    /* Scenario Active Pills */
    button[id^="pill-"].bg-indigo-600, button[id^="pill-"].bg-teal-700 {
      background-color: var(--indigo) !important;
      color: #FFFFFF !important;
      border: 1px solid var(--indigo) !important;
    }
    button[id^="pill-"]:not(.bg-indigo-600):not(.bg-teal-700) {
      background-color: var(--card) !important;
      color: var(--ink) !important;
      border: 1px solid var(--line) !important;
    }

    /* Drawer & Phone Frame */
    #borrowerPhoneDrawer, .phone-drawer-container {
      background-color: var(--cream) !important;
      border-left: 1px solid var(--line) !important;
    }
    .phone-bezel {
      background-color: var(--card) !important;
      border: 3px solid var(--line) !important;
    }
  </style>
"""

def update_file(filename):
    filepath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Skipping {filename}, does not exist")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip existing style block if present
    content = re.sub(r'<style id="step6-palette">.*?</style>', '', content, flags=re.DOTALL)
    
    # Insert new style right before </head>
    content = content.replace("</head>", f"{CSS_BLOCK}\n</head>")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Updated {filename} with Step 6 Palette!")

if __name__ == "__main__":
    update_file("production.html")
    update_file("index.html")
    update_file("coach.html")

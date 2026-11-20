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

      /* Step Tints */
      --purple-tint:  #EFE8FD;
      --purple-text:  #5B21B6;
      --red-tint:     #FDE8E6;
      --red-text:     #B91C1C;
      --teal-tint:    #DDF4F0;
      --teal-text:    #0A5F54;
      --saffron-tint: #FEF3C7;
      --saffron-text: #92400E;

      /* Canonical aliases */
      --bg:            var(--cream);
      --surface:       var(--card);
      --border:        var(--line);
      --text:          var(--ink);
      --text-muted:    var(--muted);
      --accent:        var(--indigo);
      --accent-soft:   var(--purple-tint);
      --accent-text:   var(--indigo);
      --warn-bg:       var(--saffron-tint);
      --warn-text:     var(--saffron-text);
      --danger-bg:     var(--red-tint);
      --danger-text:   var(--red-text);

      --font-family:   -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    /* Universal Font Family strictly preserving FontAwesome icons */
    body, body *:not(i):not([class*="fa-"]):not([class*="fas"]):not([class*="far"]):not([class*="fab"]):not([class*="fa"]) {
      font-family: var(--font-family) !important;
    }
    i, .fa, .fas, .far, .fab, .fa-solid, .fa-regular, .fa-brands, [class*="fa-"] {
      font-family: "Font Awesome 6 Free", "Font Awesome 6 Brands", "Font Awesome 5 Free", "FontAwesome" !important;
      font-style: normal !important;
      font-variant: normal !important;
      text-rendering: auto !important;
      -webkit-font-smoothing: antialiased !important;
    }

    /* Flat colours only, no gradients or shadows */
    *, *::before, *::after {
      box-shadow: none !important;
      text-shadow: none !important;
      transition: all 150ms ease-in-out;
      box-sizing: border-box;
    }
    [class*="bg-gradient-"], .shadow, .shadow-sm, .shadow-md, .shadow-lg, .shadow-xl, .shadow-2xl {
      background-image: none !important;
      box-shadow: none !important;
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
    .font-normal, span, p, td, li, input, select, textarea, div {
      font-weight: 400;
    }
    .font-medium, strong, th {
      font-weight: 500 !important;
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

    /* Canvas / Page background: --cream */
    main, .bg-slate-950, .bg-slate-950\\/50, .bg-slate-950\\/60, .bg-slate-950\\/40, .bg-slate-950\\/70, .bg-slate-950\\/80, .bg-slate-900\\/50 {
      background-color: var(--cream) !important;
    }

    /* Panels & Cards: --card */
    aside, .panel-card, .bg-slate-900:not(header), .bg-slate-800:not(header), .bg-slate-800\\/60, .bg-slate-800\\/80, .bg-slate-900\\/60, .bg-slate-900\\/80, .card {
      background-color: var(--card) !important;
    }

    /* Structural Borders: --line */
    .border-slate-800, .border-slate-700, .border-slate-800\\/80, .border-slate-800\\/60, .border-slate-900, .border-slate-600, .border-line {
      border-color: var(--line) !important;
    }

    /* Top Header: --indigo with crisp white text */
    header, .app-header, header.bg-slate-900, header.border-b, [role="banner"] {
      background-color: var(--indigo) !important;
      border-bottom: 1px solid var(--line) !important;
    }
    header h1, header h2, header h3, header span, header div, header p, header a {
      color: #FFFFFF !important;
    }
    header .text-slate-400, header .text-slate-500, header .text-slate-600, header .text-slate-300, header .text-slate-700 {
      color: rgba(255, 255, 255, 0.85) !important;
    }
    header .text-emerald-400, header .text-teal-400, header .text-indigo-400 {
      color: #A7F3D0 !important;
    }
    header [class*="border-"] {
      border-color: rgba(255, 255, 255, 0.25) !important;
    }
    header .bg-slate-950, header .bg-slate-900, header .bg-slate-800, header .bg-white\\/10, header .bg-indigo-950\\/60, header .bg-slate-950\\/70 {
      background-color: rgba(0, 0, 0, 0.25) !important;
      color: #FFFFFF !important;
    }
    
    /* Top Header Action Buttons */
    #btnToggleSim {
      background-color: var(--saffron) !important;
      color: var(--ink) !important;
      border: none !important;
      font-weight: 500 !important;
    }
    #btnToggleSim * {
      color: var(--ink) !important;
    }
    header button:not(#btnToggleSim) {
      background-color: rgba(255, 255, 255, 0.18) !important;
      color: #FFFFFF !important;
      border: 1px solid rgba(255, 255, 255, 0.35) !important;
    }
    header button:not(#btnToggleSim):hover {
      background-color: rgba(255, 255, 255, 0.3) !important;
      color: #FFFFFF !important;
    }
    header button:not(#btnToggleSim) * {
      color: #FFFFFF !important;
    }

    /* Base Text: --ink (high contrast on light card/canvas) */
    .text-white:not(header *):not(.btn-primary):not(.btn-primary *):not(button.bg-indigo-600):not(button.bg-indigo-600 *):not(button.bg-indigo-700):not(button.bg-indigo-700 *):not(.bubble-borrower):not(.bubble-borrower *):not(#audioControlBtn):not(#audioControlBtn *):not(button[id^="pill-"].bg-indigo-600):not(button[id^="pill-"].bg-indigo-600 *):not(button[id^="pill-"].bg-teal-700):not(button[id^="pill-"].bg-teal-700 *):not(.items-end .rounded-2xl):not(.items-end .rounded-2xl *),
    .text-slate-100, .text-slate-200, .text-slate-300 {
      color: var(--ink) !important;
    }

    /* Secondary / Muted Text: --muted */
    .text-slate-400, .text-slate-500, .text-slate-600 {
      color: var(--muted) !important;
    }

    /* Avatar: --saffron */
    #custAvatar, .avatar-saffron, .bg-amber-500.rounded-full {
      background-color: var(--saffron) !important;
      color: var(--ink) !important;
      font-weight: 500 !important;
    }

    /* Primary buttons: --indigo with white text */
    .btn-primary, button.bg-indigo-600, button.bg-indigo-700, #audioControlBtn {
      background-color: var(--indigo) !important;
      color: #FFFFFF !important;
      border: none !important;
    }
    .btn-primary *, button.bg-indigo-600 *, button.bg-indigo-700 *, #audioControlBtn * {
      color: #FFFFFF !important;
    }

    /* Payment & Act buttons: --saffron with high-contrast --ink text (6.99:1 contrast) */
    .btn-payment, #btnSimulatePayment, #btnDisburseToken, button.bg-amber-500, button.bg-amber-600, #btnKhataMic {
      background-color: var(--saffron) !important;
      color: var(--ink) !important;
      font-weight: 500 !important;
      border: none !important;
    }
    .btn-payment *, #btnSimulatePayment *, #btnDisburseToken *, #btnKhataMic * {
      color: var(--ink) !important;
    }
    .btn-payment:hover, #btnSimulatePayment:hover, button.bg-amber-500:hover {
      background-color: #E58E00 !important;
    }

    /* Secondary buttons (Clear Settlement, WhatsApp, etc.): clean white card with --line border */
    .btn-secondary, button.bg-slate-800, button.bg-slate-700, button.bg-slate-800\\/80, button.bg-slate-900 {
      background-color: var(--card) !important;
      border: 1px solid var(--line) !important;
      color: var(--ink) !important;
    }
    .btn-secondary:hover, button.bg-slate-800:hover, button.bg-slate-700:hover {
      background-color: var(--cream) !important;
      border-color: var(--muted) !important;
      color: var(--ink) !important;
    }
    .btn-secondary *, button.bg-slate-800 *, button.bg-slate-700 * {
      color: var(--ink) !important;
    }

    /* Passed-check chips & "Prove" step: --teal, bg #DDF4F0, text #0A5F54 */
    .chip-passed, .bg-emerald-500\\/20, .bg-teal-500\\/20, .step-prove, [class*="bg-emerald-500\\/20"], [class*="bg-teal-500\\/20"] {
      background-color: var(--teal-tint) !important;
      color: var(--teal-text) !important;
      border: 1px solid var(--teal) !important;
    }
    .chip-passed *, .bg-emerald-500\\/20 *, .bg-teal-500\\/20 *, .step-prove * {
      color: var(--teal-text) !important;
    }

    /* "Understand" step: --purple with tint #EFE8FD, text #5B21B6 */
    .step-understand, .bg-purple-500\\/20, .bg-purple-950\\/40, [class*="bg-purple-500\\/20"] {
      background-color: var(--purple-tint) !important;
      color: var(--purple-text) !important;
      border: 1px solid var(--purple) !important;
    }
    .step-understand *, .bg-purple-500\\/20 *, [class*="bg-purple-500\\/20"] * {
      color: var(--purple-text) !important;
    }

    /* "Detect" step & failures: --red with tint #FDE8E6, text #B91C1C */
    .step-detect, .bg-rose-500\\/20, .bg-red-500\\/20, [class*="bg-rose-500\\/20"], [class*="bg-red-500\\/20"] {
      background-color: var(--red-tint) !important;
      color: var(--red-text) !important;
      border: 1px solid var(--red) !important;
    }
    .step-detect *, .bg-rose-500\\/20 *, .bg-red-500\\/20 *, [class*="bg-rose-500\\/20"] * {
      color: var(--red-text) !important;
    }

    /* "Act" step: --saffron with tint #FEF3C7, text #92400E */
    .step-act, .bg-amber-500\\/20, [class*="bg-amber-500\\/20"] {
      background-color: var(--saffron-tint) !important;
      color: var(--saffron-text) !important;
      border: 1px solid var(--saffron) !important;
    }
    .step-act *, .bg-amber-500\\/20 *, [class*="bg-amber-500\\/20"] * {
      color: var(--saffron-text) !important;
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

    /* Left Sidebar */
    aside {
      background-color: var(--card) !important;
      border-right: 1px solid var(--line) !important;
    }
    aside #lenderTenantSelect {
      background-color: var(--cream) !important;
      border: 1px solid var(--line) !important;
      color: var(--ink) !important;
    }
    aside nav button {
      background-color: transparent !important;
      color: var(--muted) !important;
      border: 1px solid transparent !important;
      border-radius: 8px !important;
    }
    aside nav button:hover {
      background-color: var(--cream) !important;
      color: var(--ink) !important;
    }
    aside nav button.bg-indigo-600, aside nav button.active, aside nav button[class*="bg-indigo-600"] {
      background-color: var(--indigo) !important;
      color: #FFFFFF !important;
      border: 1px solid var(--indigo) !important;
    }
    aside nav button.bg-indigo-600 *, aside nav button.active * {
      color: #FFFFFF !important;
    }
    aside nav button #navBadgeQueue {
      background-color: #F0E6D2 !important;
      color: var(--ink) !important;
    }
    aside nav button.bg-indigo-600 #navBadgeQueue {
      background-color: rgba(255, 255, 255, 0.25) !important;
      color: #FFFFFF !important;
    }

    /* Accounts Table Rows */
    #accountsTableContainer > div {
      border-bottom: 1px solid var(--line) !important;
      background-color: var(--card) !important;
      transition: background-color 150ms ease;
    }
    #accountsTableContainer > div:hover {
      background-color: #FAF7F0 !important;
    }
    #accountsTableContainer > div.bg-indigo-950\\/50, 
    #accountsTableContainer > div[class*="border-indigo-500"],
    #accountsTableContainer > div[class*="border-l-4"] {
      background-color: var(--purple-tint) !important;
      border-left: 4px solid var(--indigo) !important;
    }
    #accountsTableContainer > div.bg-indigo-950\\/50 .text-white,
    #accountsTableContainer > div .font-bold {
      color: var(--ink) !important;
    }
    #accountsTableContainer > div .text-slate-400 {
      color: var(--muted) !important;
    }

    /* Scenario Active Pills */
    button[id^="pill-"].bg-indigo-600, button[id^="pill-"].bg-teal-700, button[id^="pill-"].active {
      background-color: var(--indigo) !important;
      color: #FFFFFF !important;
      border: 1px solid var(--indigo) !important;
    }
    button[id^="pill-"].bg-indigo-600 *, button[id^="pill-"].bg-teal-700 * {
      color: #FFFFFF !important;
    }
    button[id^="pill-"]:not(.bg-indigo-600):not(.bg-teal-700):not(.active) {
      background-color: var(--card) !important;
      color: var(--ink) !important;
      border: 1px solid var(--line) !important;
    }
    button[id^="pill-"]:hover {
      background-color: #FAF7F0 !important;
    }

    /* Tabs (Call Dialogue, Settlement Rails, Call Plan, etc.) */
    div[id^="tabBtn-"], button[id^="tabBtn-"] {
      color: var(--muted) !important;
      border-bottom: 2px solid transparent !important;
      font-weight: 400 !important;
      transition: all 150ms ease;
    }
    div[id^="tabBtn-"]:hover, button[id^="tabBtn-"]:hover {
      color: var(--ink) !important;
    }
    div[id^="tabBtn-"].text-indigo-400, button[id^="tabBtn-"].text-indigo-400,
    div[id^="tabBtn-"].border-indigo-500, button[id^="tabBtn-"].border-indigo-500,
    button[id^="tabBtn-"].border-b-2 {
      color: var(--indigo) !important;
      border-bottom-color: var(--indigo) !important;
      font-weight: 500 !important;
    }
    button[id^="tabBtn-"] i {
      color: inherit !important;
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
    .phone-screen {
      background-color: var(--cream) !important;
    }

    /* Form controls */
    input, select, textarea {
      background-color: var(--card) !important;
      border: 1px solid var(--line) !important;
      color: var(--ink) !important;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--indigo) !important;
      outline: none !important;
    }
    input::placeholder, textarea::placeholder {
      color: var(--muted) !important;
    }

    /* Modals */
    #roiModal, #paymentModal, .modal-backdrop {
      background-color: rgba(43, 36, 56, 0.5) !important;
    }
    #roiModal > div, #paymentModal > div, .modal-card {
      background-color: var(--card) !important;
      border: 1px solid var(--line) !important;
    }

    /* Tables across audit, callplan, outcomes */
    table {
      border-color: var(--line) !important;
    }
    thead tr {
      background-color: #FAF7F0 !important;
      border-bottom: 1px solid var(--line) !important;
    }
    thead th {
      color: var(--muted) !important;
      font-size: 12px !important;
      font-weight: 500 !important;
    }
    tbody tr {
      background-color: var(--card) !important;
      border-bottom: 1px solid var(--line) !important;
    }
    tbody tr:hover {
      background-color: #FAF7F0 !important;
    }
    td {
      color: var(--ink) !important;
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

    # Strip existing step6-palette style block if present
    content = re.sub(r'<style id="step6-palette">.*?</style>', '', content, flags=re.DOTALL)
    
    # Also strip any older Teal style block (which defined :root with --bg: #F7F6F2)
    content = re.sub(r'<style>\s*:root\s*\{\s*--bg:\s*#F7F6F2;.*?</style>', '', content, flags=re.DOTALL)

    # Insert new style right before </head>
    content = content.replace("</head>", f"{CSS_BLOCK}\n</head>")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Updated {filename} with Step 6 Palette!")

if __name__ == "__main__":
    update_file("production.html")
    update_file("index.html")
    update_file("coach.html")

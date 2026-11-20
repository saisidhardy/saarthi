import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6] # completely blank layout

    # Color Palette Constants
    COLOR_BG = RGBColor(255, 249, 240)      # Cream #FFF9F0
    COLOR_CARD = RGBColor(255, 255, 255)    # White #FFFFFF
    COLOR_LINE = RGBColor(240, 230, 210)    # Line #F0E6D2
    COLOR_INK = RGBColor(43, 36, 56)        # Ink #2B2438
    COLOR_MUTED = RGBColor(122, 111, 138)   # Muted #7A6F8A
    COLOR_INDIGO = RGBColor(42, 47, 143)    # Indigo #2A2F8F
    COLOR_SAFFRON = RGBColor(245, 158, 11)  # Saffron #F59E0B
    COLOR_TEAL = RGBColor(15, 157, 138)     # Teal #0F9D8A
    COLOR_PURPLE = RGBColor(139, 92, 246)   # Purple #8B5CF6
    COLOR_RED = RGBColor(226, 87, 76)       # Red #E2574C

    def add_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = COLOR_BG
        bg.line.fill.background()
        return bg

    def add_header(slide, slide_num, title, subtitle, timer_badge):
        # Header banner card
        hdr = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(0.5), Inches(11.733), Inches(1.1))
        hdr.fill.solid()
        hdr.fill.fore_color.rgb = COLOR_CARD
        hdr.line.color.rgb = COLOR_LINE
        hdr.line.width = Pt(1)

        tf = hdr.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.3)
        tf.margin_top = Inches(0.1)

        # Line 1: Timer Badge + Title
        p1 = tf.paragraphs[0]
        p1.text = f"[{timer_badge}]  {title}"
        p1.font.size = Pt(18)
        p1.font.bold = True
        p1.font.color.rgb = COLOR_INDIGO
        p1.font.name = "Segoe UI"

        # Line 2: Subtitle
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(11)
        p2.font.color.rgb = COLOR_MUTED
        p2.font.name = "Segoe UI"

        # Slide Number Pill
        num_box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(11.4), Inches(0.7), Inches(0.8), Inches(0.4))
        num_box.fill.solid()
        num_box.fill.fore_color.rgb = COLOR_BG
        num_box.line.color.rgb = COLOR_LINE
        ntf = num_box.text_frame
        ntf.vertical_anchor = MSO_ANCHOR.MIDDLE
        np = ntf.paragraphs[0]
        np.alignment = PP_ALIGN.CENTER
        np.text = f"{slide_num} / 6"
        np.font.size = Pt(10)
        np.font.bold = True
        np.font.color.rgb = COLOR_INDIGO
        np.font.name = "Segoe UI"

    def add_source_footer(slide, source_text):
        footer = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(6.8), Inches(11.733), Inches(0.45))
        footer.fill.solid()
        footer.fill.fore_color.rgb = COLOR_CARD
        footer.line.color.rgb = COLOR_LINE
        footer.line.width = Pt(1)

        tf = footer.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.25)
        p = tf.paragraphs[0]
        p.text = f"Source & Legal Basis: {source_text}"
        p.font.size = Pt(9.5)
        p.font.italic = True
        p.font.color.rgb = COLOR_MUTED
        p.font.name = "Segoe UI"

    # =========================================================================
    # SLIDE 1: TITLE & EXECUTIVE SUMMARY (0:00 - 0:30)
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    add_background(s1)

    # Main Hero Card
    hero = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.8), Inches(11.733), Inches(4.3))
    hero.fill.solid()
    hero.fill.fore_color.rgb = COLOR_CARD
    hero.line.color.rgb = COLOR_LINE
    hero.line.width = Pt(1.5)

    htf = hero.text_frame
    htf.margin_left = Inches(0.6)
    htf.margin_top = Inches(0.5)

    hp1 = htf.paragraphs[0]
    hp1.text = "SAARTHI  |  AI RECOVERY CLOUD"
    hp1.font.size = Pt(12)
    hp1.font.bold = True
    hp1.font.color.rgb = COLOR_TEAL
    hp1.font.name = "Segoe UI"

    hp2 = htf.add_paragraph()
    hp2.text = "The Auditable AI Collections Teammate for Indian Regulated Lenders"
    hp2.font.size = Pt(28)
    hp2.font.bold = True
    hp2.font.color.rgb = COLOR_INDIGO
    hp2.font.name = "Segoe UI"

    hp3 = htf.add_paragraph()
    hp3.text = "Headless Intelligence Middleware Sitting Invisibly Inside FinnOne & LeadSquared with Direct BYOT SIP Trunking"
    hp3.font.size = Pt(14)
    hp3.font.color.rgb = COLOR_MUTED
    hp3.font.name = "Segoe UI"

    hp4 = htf.add_paragraph()
    hp4.text = "\n• Dual-Loop Propose-vs-Decide Engine: Zero autonomous waivers, deterministic RBI policy firewall."
    hp4.font.size = Pt(12)
    hp4.font.color.rgb = COLOR_INK
    hp4.font.name = "Segoe UI"

    hp5 = htf.add_paragraph()
    hp5.text = "• Human-Grade Indic Voice: Hindi, Telugu, Marathi, Tamil, Kannada, Gujarati, Bengali & English at <500ms."
    hp5.font.size = Pt(12)
    hp5.font.color.rgb = COLOR_INK
    hp5.font.name = "Segoe UI"

    hp6 = htf.add_paragraph()
    hp6.text = "• Consent-First Cash-Flow Coach: 90-day Account Aggregator insights yielding ₹840 fee avoidance & ₹2,840 interest cut."
    hp6.font.size = Pt(12)
    hp6.font.color.rgb = COLOR_INK
    hp6.font.name = "Segoe UI"

    # Stat Badges at Bottom of Slide 1
    stats = [
        ("₹40+ LAKH CR", "Retail Credit TAM", COLOR_INDIGO),
        ("220 BPS", "Roll-Rate Reduction", COLOR_TEAL),
        ("60% SAVINGS", "vs. Agency Call Centers", COLOR_SAFFRON),
        ("100% AUDIT", "SHA-256 Defensibility", COLOR_PURPLE)
    ]
    for i, (metric, label, col) in enumerate(stats):
        bx = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 3.0), Inches(5.35), Inches(2.733), Inches(1.2))
        bx.fill.solid()
        bx.fill.fore_color.rgb = COLOR_CARD
        bx.line.color.rgb = COLOR_LINE
        btf = bx.text_frame
        btf.vertical_anchor = MSO_ANCHOR.MIDDLE
        btf.margin_left = Inches(0.2)
        bp1 = btf.paragraphs[0]
        bp1.text = metric
        bp1.font.size = Pt(20)
        bp1.font.bold = True
        bp1.font.color.rgb = col
        bp1.font.name = "Segoe UI"
        bp2 = btf.add_paragraph()
        bp2.text = label
        bp2.font.size = Pt(10)
        bp2.font.color.rgb = COLOR_MUTED
        bp2.font.name = "Segoe UI"

    add_source_footer(s1, "RBI Report on Trend and Progress of Banking in India; CRIF High Mark Retail Lending Pulse; TransUnion CIBIL.")
    s1.notes_slide.notes_text_frame.text = (
        "Good morning. Indian retail lending has surpassed ₹40 Lakh Crore, but early collections is broken. "
        "Every quarter, 4 million borrowers roll into 1–30 DPD. Saarthi is the autonomous AI collections teammate "
        "built specifically for regulated Indian lending, sitting headlessly behind core LMS systems to cut roll rates by 220 bps."
    )

    # =========================================================================
    # SLIDE 2: THE COLLECTIONS CRISIS (0:00 - 0:30)
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    add_background(s2)
    add_header(s2, 2, "The Collections Crisis & The Regulatory Squeeze", 
               "Why traditional outsourced tele-calling agencies are failing Indian Bank & NBFC Chief Risk Officers", "0:00 – 0:30")

    # 3 Column Cards
    col_w = Inches(3.644)
    # Col 1: Operational Breakdown
    c1 = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), col_w, Inches(4.7))
    c1.fill.solid()
    c1.fill.fore_color.rgb = COLOR_CARD
    c1.line.color.rgb = COLOR_LINE
    tf1 = c1.text_frame
    tf1.margin_left = Inches(0.25)
    tf1.margin_top = Inches(0.3)
    p = tf1.paragraphs[0]
    p.text = "OPERATIONAL COLLAPSE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_RED
    p = tf1.add_paragraph()
    p.text = "Agency Turnover & Cost"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf1.add_paragraph()
    p.text = "\n• 50% monthly agent attrition across outsourced recovery BPOs.\n\n• ₹18,000 to ₹22,000 monthly cost per caller seat with low training depth.\n\n• Massive managerial overhead reconciling agency files and disputed promise-to-pay claims."
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    # Col 2: The Contactability Abyss
    c2 = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.844), Inches(1.8), col_w, Inches(4.7))
    c2.fill.solid()
    c2.fill.fore_color.rgb = COLOR_CARD
    c2.line.color.rgb = COLOR_LINE
    tf2 = c2.text_frame
    tf2.margin_left = Inches(0.25)
    tf2.margin_top = Inches(0.3)
    p = tf2.paragraphs[0]
    p.text = "CONTACTABILITY FAILURE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_SAFFRON
    p = tf2.add_paragraph()
    p.text = "The Truecaller Spam Abyss"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf2.add_paragraph()
    p.text = "\n• Virtual dialler numbers get flagged as 'Spam / Recovery' in Truecaller within 48 hours.\n\n• Live call connect rates drop below 12%–18% across 1–30 DPD buckets.\n\n• Borrowers actively evade unfamiliar pooled mobile numbers, causing roll rate slippage."
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    # Col 3: The Regulatory Guillotine
    c3 = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.888), Inches(1.8), col_w, Inches(4.7))
    c3.fill.solid()
    c3.fill.fore_color.rgb = COLOR_CARD
    c3.line.color.rgb = COLOR_LINE
    tf3 = c3.text_frame
    tf3.margin_left = Inches(0.25)
    tf3.margin_top = Inches(0.3)
    p = tf3.paragraphs[0]
    p.text = "REGULATORY THREAT"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_RED
    p = tf3.add_paragraph()
    p.text = "RBI Fair Practices Penalties"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf3.add_paragraph()
    p.text = "\n• Strict enforcement of Digital Lending Guidelines & Fair Practices Code.\n\n• Dialing outside 08:00–19:00 IST or unrecorded verbal coercion triggers multi-crore fines.\n\n• Reputational risk and potential license freezes on digital lending onboarding."
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    add_source_footer(s2, "RBI Fair Practices Code for NBFCs; CRIF High Mark Retail Lending Pulse; TRAI TCCCPR Regulations.")
    s2.notes_slide.notes_text_frame.text = (
        "Early collections is broken due to 50% agency attrition, Truecaller spam blocking that drops connect rates below 15%, "
        "and strict RBI rules against harassment and off-hour dialing. Lenders face massive regulatory liabilities with third-party agencies."
    )

    # =========================================================================
    # SLIDE 3: THE SOLUTION – HEADLESS LMS & INDIC VOICE (0:30 - 1:05)
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    add_background(s3)
    add_header(s3, 3, "The Headless Solution: Invisible Middleware & Indic Voice", 
               "Plugs directly behind FinnOne & LeadSquared while originating calls via BYOT registered SIP trunks", "0:30 – 1:05")

    # Left: Headless LMS & BYOT Architecture
    c_left = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), Inches(5.666), Inches(4.7))
    c_left.fill.solid()
    c_left.fill.fore_color.rgb = COLOR_CARD
    c_left.line.color.rgb = COLOR_LINE
    tfl = c_left.text_frame
    tfl.margin_left = Inches(0.3)
    tfl.margin_top = Inches(0.3)
    p = tfl.paragraphs[0]
    p.text = "HEADLESS INTEGRATION ARCHITECTURE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_TEAL
    p = tfl.add_paragraph()
    p.text = "Zero Portal Friction for Operations"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tfl.add_paragraph()
    p.text = (
        "\n• Webhook Ingestion (/api/v1/cases/sync): Ingests delinquent accounts live from FinnOne Neo, Pennant, or LeadSquared."
        "\n\n• BYOT (Bring Your Own Telephony): Direct SIP trunking via Exotel, Tata Tele, or Airtel IQ with zero telephony markup."
        "\n\n• Registered 140-Series DLT Header (140921-BAJAJ): Originates from lender's official sender ID with Truecaller Verified Business status, doubling pickup rates."
        "\n\n• AWS Mumbai (ap-south-1) VPC: Operates entirely inside the bank's secure private cloud boundary. 100% DPDP Act compliance."
    )
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    # Right: Indic Voice Stack
    c_right = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.866), Inches(1.8), Inches(5.666), Inches(4.7))
    c_right.fill.solid()
    c_right.fill.fore_color.rgb = COLOR_CARD
    c_right.line.color.rgb = COLOR_LINE
    tfr = c_right.text_frame
    tfr.margin_left = Inches(0.3)
    tfr.margin_top = Inches(0.3)
    p = tfr.paragraphs[0]
    p.text = "SARVAM INDIC VOICE STACK"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_PURPLE
    p = tfr.add_paragraph()
    p.text = "Natural Human-Grade Regional Speech"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tfr.add_paragraph()
    p.text = (
        "\n• 8 Indian Languages Supported: Hindi, Marathi, Telugu, Tamil, Kannada, Gujarati, Bengali, and Indian English."
        "\n\n• Sub-500ms End-to-End Latency: Natural interruptibility and turn-taking without awkward pauses."
        "\n\n• Code-Mixed Colloquial Dialects: Understands complex Hinglish/Telugish borrower objections, festival delays, and wage cycles."
        "\n\n• Empathetic Tone Modulation: Maintains professional, respectful tone even during high-friction borrower interactions."
    )
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    add_source_footer(s3, "NPCI eNACH Operational Guidelines; Sarvam AI Indic Benchmarks; Saarthi Architecture Specification v2.1.")
    s3.notes_slide.notes_text_frame.text = (
        "Saarthi is an invisible, headless intelligence layer that plugs directly into FinnOne or LeadSquared. "
        "Through BYOT SIP trunking, calls go out from the bank's own 140-series registered numbers with Truecaller Verified status, "
        "speaking fluent regional Indic languages with sub-500ms response time."
    )

    # =========================================================================
    # SLIDE 4: THE MOAT – DETERMINISTIC POLICY FIREWALL (1:05 - 1:40)
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    add_background(s4)
    add_header(s4, 4, "The Compliance Moat: Deterministic Policy Firewall", 
               "Dual-Loop Propose-vs-Decide architecture eliminates generative AI hallucination risk and regulatory exposure", "1:05 – 1:40")

    # 3 Horizontal Strategy Cards
    card_h = Inches(1.4)
    y_starts = [Inches(1.8), Inches(3.45), Inches(5.1)]

    # Card 1: Propose-vs-Decide
    cd1 = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), y_starts[0], Inches(11.733), card_h)
    cd1.fill.solid()
    cd1.fill.fore_color.rgb = COLOR_CARD
    cd1.line.color.rgb = COLOR_LINE
    tf = cd1.text_frame
    tf.margin_left = Inches(0.3)
    tf.margin_top = Inches(0.18)
    p = tf.paragraphs[0]
    p.text = "PROPOSE-VS-DECIDE DUAL-LOOP ARCHITECTURE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf.add_paragraph()
    p.text = "The LLM is strictly quarantined to speech understanding. It only proposes options. Hardcoded YAML policy rules decide and clamp all agreements. Zero autonomous loan interest waivers permitted; extensions clamped strictly to ≤ 7 days."
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    # Card 2: Fair Practices & Relief Routing
    cd2 = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), y_starts[1], Inches(11.733), card_h)
    cd2.fill.solid()
    cd2.fill.fore_color.rgb = COLOR_CARD
    cd2.line.color.rgb = COLOR_LINE
    tf = cd2.text_frame
    tf.margin_left = Inches(0.3)
    tf.margin_top = Inches(0.18)
    p = tf.paragraphs[0]
    p.text = "STRICT RBI FAIR PRACTICES CODE & HOSPICASH RELIEF"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_SAFFRON
    p = tf.add_paragraph()
    p.text = "Mandatory 08:00–19:00 IST calling window enforced at the gateway. Real-time anti-coercion tripwires block aggressive vocabulary. Disclosures of hospitalization or death immediately trigger a sensitive pause and auto-file Hospicash insurance rider claims."
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    # Card 3: Cryptographic Evidence Pack
    cd3 = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), y_starts[2], Inches(11.733), card_h)
    cd3.fill.solid()
    cd3.fill.fore_color.rgb = COLOR_CARD
    cd3.line.color.rgb = COLOR_LINE
    tf = cd3.text_frame
    tf.margin_left = Inches(0.3)
    tf.margin_top = Inches(0.18)
    p = tf.paragraphs[0]
    p.text = "CRYPTOGRAPHIC SHA-256 AUDIT EVIDENCE PACK"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_TEAL
    p = tf.add_paragraph()
    p.text = "Every borrower conversation auto-generates a tamper-evident SHA-256 evidence package containing verbatim transcripts, dual-channel audio recordings, rule ID citations, and timestamped decision traces—instantly defensible before RBI Ombudsman audits."
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    add_source_footer(s4, "RBI Digital Lending Guidelines (Sec 5.2); ISO/IEC 27001 Audit Standard; Saarthi collections_rules.yaml.")
    s4.notes_slide.notes_text_frame.text = (
        "Generative AI only proposes options; our hardcoded policy firewall decides and enforces rules. "
        "Unauthorized interest waivers are mathematically blocked. Medical emergencies trigger sensitive relief riders. "
        "Every interaction produces a cryptographic SHA-256 Evidence Pack ready for RBI ombudsman audits."
    )

    # =========================================================================
    # SLIDE 5: CASH-FLOW COACH & REPAYMENT GAINS (1:40 - 2:15)
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    add_background(s5)
    add_header(s5, 5, "Borrower Financial Health: Cash-Flow Check-Up & Incentives", 
               "Consent-first Account Aggregator analytics turning 90 days of transactions into positive borrower savings", "1:40 – 2:15")

    # 3 Borrower Incentive Stat Cards
    c_w = Inches(3.644)
    # Card 1: Fee Avoidance
    g1 = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), c_w, Inches(2.3))
    g1.fill.solid()
    g1.fill.fore_color.rgb = COLOR_CARD
    g1.line.color.rgb = COLOR_LINE
    tf = g1.text_frame
    tf.margin_left = Inches(0.2)
    tf.margin_top = Inches(0.2)
    p = tf.paragraphs[0]
    p.text = "INSTANT CASH SAVED"
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = COLOR_TEAL
    p = tf.add_paragraph()
    p.text = "Save ₹840.00"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf.add_paragraph()
    p.text = "Avoids ₹590 eNACH bounce charge plus ₹250 penal late fee by settling on or before high-inflow day."
    p.font.size = Pt(10)
    p.font.color.rgb = COLOR_INK

    # Card 2: Accelerated Payoff
    g2 = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.844), Inches(1.8), c_w, Inches(2.3))
    g2.fill.solid()
    g2.fill.fore_color.rgb = COLOR_CARD
    g2.line.color.rgb = COLOR_LINE
    tf = g2.text_frame
    tf.margin_left = Inches(0.2)
    tf.margin_top = Inches(0.2)
    p = tf.paragraphs[0]
    p.text = "EARLY LOAN FREEDOM"
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = COLOR_PURPLE
    p = tf.add_paragraph()
    p.text = "Save ₹2,840 Interest"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf.add_paragraph()
    p.text = "Adding ₹500/week cuts loan tenure by 1–2 months, slashing total interest paid without cashflow strain."
    p.font.size = Pt(10)
    p.font.color.rgb = COLOR_INK

    # Card 3: CIBIL Protection
    g3 = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.888), Inches(1.8), c_w, Inches(2.3))
    g3.fill.solid()
    g3.fill.fore_color.rgb = COLOR_CARD
    g3.line.color.rgb = COLOR_LINE
    tf = g3.text_frame
    tf.margin_left = Inches(0.2)
    tf.margin_top = Inches(0.2)
    p = tf.paragraphs[0]
    p.text = "CREDIT GROWTH & UPGRADES"
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = COLOR_SAFFRON
    p = tf.add_paragraph()
    p.text = "748+ CIBIL Protected"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = tf.add_paragraph()
    p.text = "Prevents a 40–60 point bureau penalty, unlocking ₹50,000 pre-approved top-ups at 2.5% lower APR."
    p.font.size = Pt(10)
    p.font.color.rgb = COLOR_INK

    # Bottom Banner: WhatsApp Positive Handoff
    wa = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(4.3), Inches(11.733), Inches(2.2))
    wa.fill.solid()
    wa.fill.fore_color.rgb = COLOR_CARD
    wa.line.color.rgb = COLOR_TEAL
    wa.line.width = Pt(1.5)
    watf = wa.text_frame
    watf.margin_left = Inches(0.3)
    watf.margin_top = Inches(0.2)
    p = watf.paragraphs[0]
    p.text = "POSITIVE REINFORCEMENT: 1-CLICK WHATSAPP DISPATCH"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_TEAL
    p = watf.add_paragraph()
    p.text = (
        "Empathetic, data-grounded WhatsApp messages in English & Hindi sent directly to the borrower: "
        "'Hi Sunita, clearing your overdue payment by Monday saves you ₹840 in bank bounce charges, cuts ₹2,840 in interest "
        "if you pay ₹500 extra weekly, and protects your 748+ CIBIL score for a pre-approved ₹50,000 working capital top-up. "
        "Tap here to view your savings and pay safely: saarthi.embarko.app/pay/kirana_owner'"
    )
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    add_source_footer(s5, "RBI Account Aggregator Master Directions; SIDBI MSME Pulse; Saarthi Cash-Flow Engine (/policies/coach.yaml).")
    s5.notes_slide.notes_text_frame.text = (
        "We replace threats with positive financial gains. Our Cash-Flow Coach turns 90 days of Account Aggregator bank transactions "
        "into clear incentives: Save ₹840 in bounce fees, cut ₹2,840 in interest via micro-prepayments, and protect a 745+ CIBIL score "
        "for a ₹50,000 top-up credit line. Dispatched directly via WhatsApp in English and Hindi."
    )

    # =========================================================================
    # SLIDE 6: FOUR FITS & BUSINESS CASE (2:15 - 3:00)
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    add_background(s6)
    add_header(s6, 6, "Four Fits Strategy & Enterprise Business Case", 
               "Superior software gross margins combined with an irresistible ROI for retail lending institutions", "2:15 – 3:00")

    # Left: Four Fits Strategy
    ff_box = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), Inches(5.666), Inches(4.7))
    ff_box.fill.solid()
    ff_box.fill.fore_color.rgb = COLOR_CARD
    ff_box.line.color.rgb = COLOR_LINE
    fft = ff_box.text_frame
    fft.margin_left = Inches(0.3)
    fft.margin_top = Inches(0.3)
    p = fft.paragraphs[0]
    p.text = "THE FOUR FITS STRATEGIC ALIGNMENT"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = fft.add_paragraph()
    p.text = (
        "\n• Product <-> Channel Fit Solved: Shifted from standalone portal to invisible headless API. "
        "Runs as a Docker container directly inside the lender's AWS Mumbai (ap-south-1) VPC, eliminating Infosec/DPDP data residency friction."
        "\n\n• Channel <-> Model Fit Solved: Replaced low-ticket per-minute billing with predictable enterprise licensing. "
        "BYOT direct SIP trunking eliminates 60% of telephony COGS, protecting software gross margins above 80%."
        "\n\n• Model <-> Market Fit: Outcompetes human BPO seat costs (₹20,000/mo) while delivering 100% compliance auditability."
    )
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    # Right: Quantitative ROI & Pricing
    roi_box = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.866), Inches(1.8), Inches(5.666), Inches(4.7))
    roi_box.fill.solid()
    roi_box.fill.fore_color.rgb = COLOR_CARD
    roi_box.line.color.rgb = COLOR_TEAL
    roi_box.line.width = Pt(1.5)
    rt = roi_box.text_frame
    rt.margin_left = Inches(0.3)
    rt.margin_top = Inches(0.3)
    p = rt.paragraphs[0]
    p.text = "ENTERPRISE ROI & HYBRID PRICING"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_TEAL
    p = rt.add_paragraph()
    p.text = "Per 10,000 Delinquent Loans / Month:"
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = COLOR_INDIGO
    p = rt.add_paragraph()
    p.text = (
        "\n• 220 bps Roll-Rate Reduction: Prevents ₹42.5 Lakhs in bad-debt provisions."
        "\n\n• 60% Agency Cost Cut: Reduces collection agency OPEX from ₹2.1 Cr to ₹84 Lakhs/yr."
        "\n\n• Predictable Hybrid Pricing Tier:"
        "\n   - Base Platform License: ₹24 Lakhs / yr (VPC deploy + Policy updates)"
        "\n   - Success Surcharge: ₹75 per cured 1–30 DPD account (auto-reconciled)"
        "\n   - Telephony: 0% Markup (Direct to Exotel/Tata at ~₹0.30/min)"
        "\n\n• 48-Hour Sandbox Integration via standard webhooks."
    )
    p.font.size = Pt(11)
    p.font.color.rgb = COLOR_INK

    add_source_footer(s6, "Saarthi 25-Account Empirical Portfolio Simulation; TransUnion CIBIL Industry Roll-Rate Studies (Retail NBFC Segment).")
    s6.notes_slide.notes_text_frame.text = (
        "For an NBFC managing 10,000 early delinquent loans a month, Saarthi prevents ₹42 Lakhs in bad-debt provisions "
        "while slashing collection agency costs by 60%. Priced simply at ₹24 Lakhs annual platform license plus ₹75 per cured account. "
        "We are live and ready for pilot integration within 48 hours. Thank you."
    )

    # Save Deck to Multiple Paths
    out_paths = [
        r"C:\Users\vajja\saarthi\saarthi_pitch_deck_3min.pptx",
        r"C:\Users\vajja\saarthi\static\saarthi_pitch_deck_3min.pptx",
        r"C:\Users\vajja\.gemini\antigravity\brain\378e15b6-7f1a-4039-8434-e51ecdd5dd6e\saarthi_pitch_deck_3min.pptx"
    ]

    for p in out_paths:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        prs.save(p)
        print(f"Presentation successfully saved to: {p} ({os.path.getsize(p)} bytes)")

if __name__ == "__main__":
    create_deck()

import os
import sys
import csv
import json
import time
import re
from typing import Dict, Any, List
from dotenv import load_dotenv

# Ensure saarthi root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
api_key = os.getenv("SARVAM_API_KEY")

SAMPLE_BOOK_PATH = os.path.join(PROJECT_ROOT, "data", "sample_book.csv")
OUTPUT_JSON_PATH = os.path.join(PROJECT_ROOT, "data", "scripts.json")

def generate_with_sarvam(client, prompt: str, system_prompt: str) -> str:
    res = client.chat.completions(
        model="sarvam-105b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=4000
    )
    msg = res.choices[0].message
    if msg.content:
        return msg.content
    elif hasattr(msg, "reasoning_content") and msg.reasoning_content:
        return msg.reasoning_content
    return ""

def build_curated_indic_script(row: Dict[str, str]) -> Dict[str, Any]:
    acc_id = str(row.get("id"))
    name = row.get("borrower_name", "")
    lang = row.get("language", "Hindi")
    amt = float(row.get("amount_due", 0))
    dpd = int(row.get("dpd", 0))
    loan_id = row.get("loan_id", "LN-1001")
    scenario = row.get("scenario", "ptp")
    last_4 = re.sub(r"\D", "", loan_id)[-4:] if loan_id else "1001"

    if acc_id == "1":
        # Hero: Sunita Patil (Pune Paytm QR merchant)
        dialogue = [
            {
                "turn": 1,
                "speaker": "agent",
                "text": f"नमस्कार सुनिताजी, मी सारथी फायनान्शियल कडून बोलतेय. हा कॉल सुरक्षेसाठी रेकॉर्ड केला जातोय. सुरक्षेसाठी आपल्या लोनचे शेवटचे ४ अंक सांगाल का?",
                "translation": f"Hello Sunitaji, I am calling from Saarthi Financial. This call is being recorded for regulatory security. For verification, could you confirm the last 4 digits of your loan?"
            },
            {
                "turn": 2,
                "speaker": "borrower",
                "text": f"हो, {last_4} आहे. बोला काय काम होतं?",
                "translation": f"Yes, it is {last_4}. Tell me, what was the matter?"
            },
            {
                "turn": 3,
                "speaker": "agent",
                "text": f"धन्यवाद सुनिताजी, ओळखीची पुष्टी झाली आहे. आपल्या लोन खात्यावर ₹{amt:,.0f} चा ईएमआय {dpd} दिवसांपासून थकला आहे. आज भरणा करू शकाल का?",
                "translation": f"Thank you Sunitaji, identity confirmed. Your loan account has an overdue EMI of ₹{amt:,.0f} for {dpd} days. Can you make the payment today?"
            },
            {
                "turn": 4,
                "speaker": "borrower",
                "text": f"अहो ताई, माझा पुण्यात किराणा दुकानाचा धंदा आहे. सगळे गिऱ्हाईक आणि Paytm QR चे पैसे महिन्याच्या 5 तारखेला जमा होतात. मी 5 तारखेला नक्की सर्व ₹{amt:,.0f} भरून टाकते.",
                "translation": f"Look madam, I run a grocery shop in Pune. All customer and Paytm QR receipts get credited on the 5th of the month. I will definitely pay the full ₹{amt:,.0f} on the 5th."
            },
            {
                "turn": 5,
                "speaker": "agent",
                "text": "नक्कीच सुनिताजी, आम्ही 5 तारखेची मुदत (PTP) नोंदवून घेतली आहे. आपल्या सोयीसाठी व्हॉट्सॲपवर UPI पेमेंट लिंक पाठवत आहोत. धन्यवाद!",
                "translation": "Certainly Sunitaji, we have recorded your Promise to Pay (PTP) for the 5th. We are sending a UPI payment link on WhatsApp for your convenience. Thank you!"
            }
        ]
        b_script = f"हो, माझा लोन नंबर {last_4} आहे. माझा पुण्यात Paytm QR चा किराणा धंदा आहे, 5 तारखेला दुकानाचे पैसे येतात. मी 5 तारखेला नक्की सर्व ₹{amt:,.0f} थकीत ईएमआय भरेन."
        b_script_en = f"Yes, my loan number is {last_4}. I run a grocery store in Pune with Paytm QR, shop earnings arrive on the 5th. I will definitely pay the full ₹{amt:,.0f} overdue EMI on the 5th."
        a_script = "नमस्कार सुनिताजी, ओळखीची पुष्टी झाली आहे. आम्ही 5 तारखेचा प्रॉमिस-टू-पे (PTP) नोंदवला आहे. आपल्या सोयीसाठी व्हॉट्सॲपवर UPI पेमेंट लिंक पाठवली आहे. धन्यवाद."
        a_script_en = "Hello Sunitaji, identity confirmed. We have recorded a Promise to Pay (PTP) for the 5th. A UPI payment link has been dispatched via WhatsApp. Thank you."

    elif acc_id == "2":
        # Dispute: Rajesh Sharma
        dialogue = [
            {
                "turn": 1,
                "speaker": "agent",
                "text": f"नमस्ते {name} जी, मैं सारथी फाइनेंशियल से बोल रहा हूँ। यह कॉल गुणवत्ता और अनुपालन निगरानी के लिए रिकॉर्ड की जा रही है। सुरक्षा के लिए लोन अकाउंट के आखिरी 4 अंक बताइए?",
                "translation": f"Hello {name} ji, calling from Saarthi Financial. This call is recorded for compliance. For verification, please share the last 4 digits of your loan account?"
            },
            {
                "turn": 2,
                "speaker": "borrower",
                "text": f"हाँ, {last_4} ही है। अरे भाई, मैं तो 2 दिन पहले ही पूरे ₹{amt:,.0f} Google Pay से भर चुका हूँ! मेरे खाते से कट गए हैं, दोबारा फोन क्यों कर रहे हो?",
                "translation": f"Yes, it is {last_4}. Brother, I already paid the full ₹{amt:,.0f} via Google Pay 2 days ago! It got debited from my account, why are you calling again?"
            },
            {
                "turn": 3,
                "speaker": "agent",
                "text": "राजेश जी, यदि आपके खाते से कटौती हो चुकी है, तो हम इस मामले को तुरंत हमारी सीनियर ऑपरेशंस टीम को हैंडऑफ कर रहे हैं ताकि बैंक स्टेटमेंट वेरीफाई किया जा सके।",
                "translation": "Rajesh ji, if the amount was already debited from your account, we are immediately escalating this case to our Senior Operations desk to verify your bank statement."
            }
        ]
        b_script = f"हाँ, लोन {last_4} ही है। अरे भाई, मैं तो 2 दिन पहले ही पूरे पैसे भर चुका हूँ! मेरे खाते से कट गए हैं, दोबारा फोन क्यों कर रहे हो?"
        b_script_en = f"Yes, loan is {last_4}. Brother, I already paid in full 2 days ago! Deducted from my bank, why are you calling again?"
        a_script = "राजेश जी, यदि आपके खाते से कटौती हो चुकी है, तो हम इस मामले को तुरंत हमारी सीनियर ऑपरेशंस टीम को हैंडऑफ कर रहे हैं ताकि बैंक स्टेटमेंट वेरीफाई किया जा सके।"
        a_script_en = "Rajesh ji, if deduction already happened, we are immediately handing off to our senior ops team to verify bank records."

    elif acc_id == "3":
        # Hardship: Suresh Patil (Hospital / Shortfall > ₹10k)
        dialogue = [
            {
                "turn": 1,
                "speaker": "agent",
                "text": f"नमस्कार {name}जी, सारथी फायनान्शियल कडून कॉल आहे. सुरक्षेसाठी आपल्या लोनचे शेवटचे ४ अंक सांगा?",
                "translation": f"Hello {name}ji, calling from Saarthi Financial. For security please share the last 4 digits of your loan?"
            },
            {
                "turn": 2,
                "speaker": "borrower",
                "text": f"हो {last_4} आहे. अहो भाऊ, माझे वडील हॉस्पिटलमध्ये ऍडमिट आहेत, खूप मोठा खर्च झाला आहे. मला व्याजात सूट किंवा कर्जाची पुनर्रचना करून मिळेल का?",
                "translation": f"Yes it is {last_4}. Brother, my father is admitted in the hospital, incurred huge medical expenses. Can I get an interest waiver or loan restructuring?"
            },
            {
                "turn": 3,
                "speaker": "agent",
                "text": "सुरेशजी, वैद्यकीय अडचणीबद्दल सहानुभूती. आमच्या पॉलिसीनुसार ₹10,000 वरील सवलतीसाठी हा प्रस्ताव वरिष्ठ क्रेडिट कमिटीकडे मंजुरीसाठी पाठवला आहे.",
                "translation": "Sureshji, sympathies for your medical emergency. As per policy, relief exceeding ₹10,000 is forwarded to the Senior Credit Committee for floor approval."
            }
        ]
        b_script = f"हो {last_4} आहे. माझे वडील हॉस्पिटलमध्ये ऍडमिट आहेत, खूप मोठा खर्च झाला आहे. मला व्याजात सूट किंवा कर्जाची पुनर्रचना करून मिळेल का?"
        b_script_en = f"Yes it is {last_4}. My father is admitted in hospital, heavy expenses. Can I get an interest waiver or EMI restructure?"
        a_script = "सुरेशजी, वैद्यकीय अडचणीबद्दल सहानुभूती. आमच्या पॉलिसीनुसार ₹10,000 वरील सवलतीसाठी हा प्रस्ताव वरिष्ठ क्रेडिट कमिटीकडे मंजुरीसाठी पाठवला आहे."
        a_script_en = "Sureshji, sympathies. As per policy, relief over ₹10k is routed to the senior credit committee for human approval."

    elif acc_id == "4":
        # Abusive Agent Test: Manoj Kumar (Compliance Violation Test)
        dialogue = [
            {
                "turn": 1,
                "speaker": "agent",
                "text": f"नमस्ते {name} जी, सारथी से कॉल है। लोन के आखिरी 4 अंक बताइए।",
                "translation": f"Hello {name} ji, call from Saarthi. Share last 4 digits of loan."
            },
            {
                "turn": 2,
                "speaker": "borrower",
                "text": f"हाँ {last_4} है। सर अभी हाथ बहुत तंग है, कृपया मुझे 2 दिन का समय दे दीजिए.",
                "translation": f"Yes it is {last_4}. Sir, money is very tight right now, please give me 2 days time."
            },
            {
                "turn": 3,
                "speaker": "agent",
                "text": "अरे तंग है तो कर्जा क्यों लिया बे? अगर आज शाम तक 12000 रुपये नहीं भरे तो तेरे घर पुलिस और रिकवरी एजेंट भेजकर पूरे मोहल्ले में बेइज्जत करवाऊंगा!",
                "translation": "If tight why did you take a loan? If you don't pay ₹12,000 by this evening I will send police and recovery goons to your house and publicly humiliate you in the entire neighborhood!"
            }
        ]
        b_script = f"हाँ {last_4} है। सर अभी हाथ तंग है, कृपया 2 दिन का समय दे दीजिए."
        b_script_en = f"Yes it is {last_4}. Sir, hand is tight right now, please give 2 days time."
        a_script = "अरे तंग है तो कर्जा क्यों लिया बे? अगर आज शाम तक 12000 रुपये नहीं भरे तो तेरे घर पुलिस और रिकवरी एजेंट भेजकर पूरे मोहल्ले में बेइज्जत करवाऊंगा!"
        a_script_en = "If tight why take a loan? If you don't pay ₹12,000 by evening I will send police and goons to your house and humiliate you in front of the whole neighborhood!"

    elif acc_id == "5":
        # Identity Failure: Kavita Rao (Zero disclosure)
        dialogue = [
            {
                "turn": 1,
                "speaker": "agent",
                "text": f"Hello {name}, calling from Saarthi Financial. This call is recorded. For privacy and security, could you please confirm the last 4 digits of your loan account?",
                "translation": f"Hello {name}, calling from Saarthi Financial. This call is recorded. For privacy and security, could you please confirm the last 4 digits of your loan account?"
            },
            {
                "turn": 2,
                "speaker": "borrower",
                "text": "Who is this? I don't know any loan number and I am not giving you any digits. Stop calling my number.",
                "translation": "Who is this? I don't know any loan number and I am not giving you any digits. Stop calling my number."
            },
            {
                "turn": 3,
                "speaker": "agent",
                "text": "For your privacy and under RBI regulations, we cannot disclose any loan details without identity verification. Ending this call.",
                "translation": "For your privacy and under RBI regulations, we cannot disclose any loan details without identity verification. Ending this call."
            }
        ]
        b_script = "Who is this? I don't know any loan number and I am not giving you any digits. Stop calling my number."
        b_script_en = "Who is this? I don't know any loan number and I am not giving you any digits. Stop calling my number."
        a_script = "For security and RBI borrower privacy, we cannot disclose loan details without verification. Ending call and escalating to verification desk."
        a_script_en = "For security and RBI borrower privacy, we cannot disclose loan details without verification. Ending call and escalating to verification desk."

    elif acc_id == "6":
        # Avoidance: Arvind Tiwari
        dialogue = [
            {
                "turn": 1,
                "speaker": "agent",
                "text": f"नमस्ते {name} जी, सारथी से कॉल है। लोन के आखिरी 4 अंक बताइए।",
                "translation": f"Hello {name} ji, call from Saarthi. Share last 4 digits of loan."
            },
            {
                "turn": 2,
                "speaker": "borrower",
                "text": f"हाँ {last_4} है। अभी मैं बहुत जरूरी मीटिंग में हूँ, बाद में बात करना, फोन काटो...",
                "translation": f"Yes it is {last_4}. Right now I am in an urgent meeting, talk later, disconnect the phone..."
            },
            {
                "turn": 3,
                "speaker": "agent",
                "text": "अरविंद जी, हमने कॉल लॉग कर ली है। आपके लिए 24 घंटे में फॉलो-अप कॉल शेड्यूल किया जा रहा है।",
                "translation": "Arvind ji, we have logged the call. A follow-up call is being scheduled for you in 24 hours."
            }
        ]
        b_script = f"हाँ {last_4} है। अभी मैं बहुत जरूरी काम में हूँ, बाद में बात करना, फोन काटो..."
        b_script_en = f"Yes it is {last_4}. Right now I am in very urgent work, talk later, disconnect the phone..."
        a_script = "अरविंद जी, हमने कॉल लॉग कर ली है। आपके लिए 24 घंटे में फॉलो-अप कॉल शेड्यूल किया जा रहा है।"
        a_script_en = "Arvind ji, we have logged the call. A follow-up call is scheduled within 24 hours."

    else:
        # Standard PTP or Part Payment accounts (colloquial Marathi, Hindi, English)
        if lang == "Marathi":
            dialogue = [
                {
                    "turn": 1,
                    "speaker": "agent",
                    "text": f"नमस्कार {name}जी, सारथी फायनान्शियल कडून कॉल आहे. सुरक्षेसाठी लोनचे शेवटचे ४ अंक सांगा?",
                    "translation": f"Hello {name}ji, calling from Saarthi Financial. For security, please share the last 4 digits of your loan?"
                },
                {
                    "turn": 2,
                    "speaker": "borrower",
                    "text": f"हो {last_4} आहे. अहो, दोन दिवसांत पैसे हातात येतील, 23 तारखेला नक्की भरून काढतो.",
                    "translation": f"Yes it is {last_4}. Look, money will be in hand in two days, I will definitely clear it on the 23rd."
                },
                {
                    "turn": 3,
                    "speaker": "agent",
                    "text": "धन्यवाद, प्रॉमिस-टू-पे (PTP) नोंदवला आहे. पेमेंट लिंक व्हॉट्सॲपवर पाठवली आहे.",
                    "translation": "Thank you, Promise-to-Pay (PTP) recorded. Payment link has been sent on WhatsApp."
                }
            ]
            b_script = f"हो {last_4} आहे. दोन दिवसांत पैसे देतो, 23 तारखेला नक्की भरतो."
            b_script_en = f"Yes it is {last_4}. I will pay within two days, will definitely pay on 23rd."
            a_script = "धन्यवाद, प्रॉमिस-टू-पे नोंदवला आहे. कृपया दिलेल्या UPI लिंकवरून वेळेवर भरणा करावा."
            a_script_en = "Thank you, PTP recorded. Please complete payment using the provided UPI link on time."
        elif lang == "English":
            dialogue = [
                {
                    "turn": 1,
                    "speaker": "agent",
                    "text": f"Hello {name}, calling from Saarthi Financial. Please confirm the last 4 digits of your loan account?",
                    "translation": f"Hello {name}, calling from Saarthi Financial. Please confirm the last 4 digits of your loan account?"
                },
                {
                    "turn": 2,
                    "speaker": "borrower",
                    "text": f"Yes, it is {last_4}. My salary got slightly delayed, but I can transfer the overdue payment by Friday evening.",
                    "translation": f"Yes, it is {last_4}. My salary got slightly delayed, but I can transfer the overdue payment by Friday evening."
                },
                {
                    "turn": 3,
                    "speaker": "agent",
                    "text": "Thank you. PTP recorded for Friday. UPI payment link dispatched.",
                    "translation": "Thank you. PTP recorded for Friday. UPI payment link dispatched."
                }
            ]
            b_script = f"Yes, last 4 digits are {last_4}. I will clear the complete EMI by Friday evening for sure."
            b_script_en = f"Yes, last 4 digits are {last_4}. I will clear the complete EMI by Friday evening for sure."
            a_script = "Understood, we have scheduled the PTP for Friday. The UPI payment link has been dispatched."
            a_script_en = "Understood, we have scheduled the PTP for Friday. The UPI payment link has been dispatched."
        else: # Hindi
            dialogue = [
                {
                    "turn": 1,
                    "speaker": "agent",
                    "text": f"नमस्ते {name} जी, सारथी से बात कर रहा हूँ। लोन अकाउंट के आखिरी 4 अंक बताइए?",
                    "translation": f"Hello {name} ji, speaking from Saarthi. Share last 4 digits of loan account?"
                },
                {
                    "turn": 2,
                    "speaker": "borrower",
                    "text": f"जी {last_4} है। कल दोपहर तक फोनपे से कर दूँगा, लिंक भेज दीजिए.",
                    "translation": f"Yes it is {last_4}. I will pay via PhonePe by tomorrow afternoon, please send link."
                },
                {
                    "turn": 3,
                    "speaker": "agent",
                    "text": "धन्यवाद, कल दोपहर तक का PTP दर्ज कर लिया गया है। UPI लिंक भेज दिया गया है।",
                    "translation": "Thank you, PTP till tomorrow afternoon recorded. UPI link dispatched."
                }
            ]
            b_script = f"जी {last_4} है। कल दोपहर तक पेमेंट कर दूँगा, कृपया लिंक भेज दीजिए."
            b_script_en = f"Yes it is {last_4}. I will pay by tomorrow afternoon, please send link."
            a_script = "जी धन्यवाद, PTP दर्ज कर लिया गया है। UPI लिंक आपको प्रेषित कर दिया गया है।"
            a_script_en = "Thank you, PTP logged. UPI link has been sent to your number."

    return {
        "account_id": acc_id,
        "borrower_name": name,
        "phone": row.get("phone", ""),
        "language": lang,
        "amount_due": amt,
        "due_date": row.get("due_date", ""),
        "dpd": dpd,
        "loan_id": loan_id,
        "scenario": scenario,
        "expected_outcome": row.get("expected_outcome", "ptp"),
        "dialogue": dialogue,
        "borrower_script": b_script,
        "borrower_script_en": b_script_en,
        "agent_script": a_script,
        "agent_script_en": a_script_en
    }

def main():
    print("=" * 60)
    print("SAARTHI SCRIPT GENERATOR: Sarvam Indic Spoken Scripts")
    print("=" * 60)

    if not os.path.exists(SAMPLE_BOOK_PATH):
        print(f"Error: {SAMPLE_BOOK_PATH} not found!")
        sys.exit(1)

    with open(SAMPLE_BOOK_PATH, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"Loaded {len(reader)} accounts from {SAMPLE_BOOK_PATH}")

    sarvam_client = None
    if api_key and api_key != "mock_sarvam_key":
        try:
            from sarvamai import SarvamAI
            sarvam_client = SarvamAI(api_subscription_key=api_key, timeout=12.0)
            print("Connected to Sarvam AI SDK (sarvam-105b).")
        except Exception as e:
            print(f"Warning: Sarvam SDK init failed ({e}).")

    generated_scripts = {}

    for row in reader:
        acc_id = str(row["id"])
        name = row["borrower_name"]
        lang = row["language"]
        amt = row["amount_due"]
        dpd = row["dpd"]
        scenario = row["scenario"]
        loan_id = row["loan_id"]
        last_4 = re.sub(r"\D", "", loan_id)[-4:] if loan_id else "1001"

        print(f"Generating Account #{acc_id:2s} ({name}, {lang}, ₹{amt}, DPD {dpd}, {scenario})...", end=" ", flush=True)

        entry = None
        if sarvam_client and acc_id in ["1"]:
            # Query Sarvam-105B specifically for colloquial nuances
            prompt = f"Write one natural Pune Marathi sentence for Sunita Patil (grocery shopkeeper, Paytm QR, Rs {amt} loan) saying her shop earnings come on the 5th and she will pay on the 5th. Be colloquial and brief."
            try:
                spoken_marathi = generate_with_sarvam(sarvam_client, prompt, "You write colloquial Pune Marathi.")
                clean_spoken = spoken_marathi.strip().split("\n")[0].replace('"', '')
                if clean_spoken:
                    entry = build_curated_indic_script(row)
                    # Enrich borrower turn 4 with Sarvam-105B generated authentic sentence
                    entry["dialogue"][3]["text"] = clean_spoken
                    entry["borrower_script"] = f"हो, {last_4} आहे. {clean_spoken}"
                    print("Done (Sarvam-105B Enhanced)")
            except Exception as e:
                print(f"[Fallback: {e}]", end=" ")

        if not entry:
            entry = build_curated_indic_script(row)
            print("Done (Curated Colloquial)")

        generated_scripts[acc_id] = entry
        time.sleep(0.05)

    # Save to data/scripts.json
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(generated_scripts, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"SUCCESS: Saved all 20 accounts to {OUTPUT_JSON_PATH}")
    print("=" * 60)

    # Print Hero Account (#1 Sunita Patil)
    hero = generated_scripts.get("1")
    if hero:
        print("\n" + "★" * 25 + " HERO ACCOUNT (#1 Sunita Patil) " + "★" * 25)
        print(f"Borrower: {hero['borrower_name']} | Language: {hero['language']} | Amount: ₹{hero['amount_due']:,.0f} | DPD: {hero['dpd']}")
        print(f"Scenario: {hero['scenario']} | Expected Outcome: {hero['expected_outcome']}\n")
        print("DIALOGUE TRANSCRIPT WITH REAL-TIME ENGLISH TRANSLATIONS:")
        print("-" * 75)
        for t in hero.get("dialogue", []):
            spk = t['speaker'].upper()
            txt = t['text']
            trans = t.get('translation', '')
            print(f"[{spk:8s}]: {txt}")
            print(f"          ↳ (English): {trans}\n")
        print("-" * 75)
        print(f"Borrower Script : {hero['borrower_script']}")
        print(f"English Trans   : {hero['borrower_script_en']}")
        print(f"Agent Script    : {hero['agent_script']}")
        print(f"English Trans   : {hero['agent_script_en']}")
        print("=" * 75)

if __name__ == "__main__":
    main()

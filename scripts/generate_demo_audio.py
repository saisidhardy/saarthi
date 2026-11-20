import asyncio
import os
import edge_tts

DEMO_SCRIPTS = {
    "demo_english.mp3": {
        "voice": "en-IN-NeerjaNeural",
        "text": "Hello Mr. Malhotra, this is Saarthi, an automated AI recovery assistant calling on behalf of Demo Lender A regarding your overdue loan repayment. As per our board-approved policy, autonomous waivers are not permitted, but we can offer an extension of up to 7 days."
    },
    "demo_hindi.mp3": {
        "voice": "hi-IN-SwaraNeural",
        "text": "नमस्ते राजेश जी, मैं सारथी हूँ, डेमो लेंडर ए की ओर से आपकी ईएमआई के संदर्भ में एआई कॉल कर रही हूँ। आपके अनुरोध पर पच्चीस सौ रुपये का अग्रिम टोकन स्वीकार कर लिया गया है, और शेष राशि के लिए शुक्रवार का ऑटो-पे मैंडेट शेड्यूल कर दिया गया है।"
    },
    "demo_telugu.mp3": {
        "voice": "te-IN-ShrutiNeural",
        "text": "నమస్కారం కవిత గారు, నేను సారథి, డెమో లెండర్ బి తరపున మీ ఈఎంఐ చెల్లింపు కోసం మాట్లాడుతున్నాను. శుక్రవారం నాడు ముప్పై రెండు వేల రూపాయల పూర్తి చెల్లింపు కోసం మీ ప్రామిస్ టు పే నమోదు చేయబడింది. ధన్యవాదాలు."
    }
}

async def generate():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "static", "audio")
    os.makedirs(out_dir, exist_ok=True)
    
    for fname, item in DEMO_SCRIPTS.items():
        fpath = os.path.join(out_dir, fname)
        print(f"Synthesizing {fname} with {item['voice']}...")
        comm = edge_tts.Communicate(item["text"], item["voice"], rate="-2%")
        audio_bytes = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        with open(fpath, "wb") as f:
            f.write(audio_bytes)
        print(f"Generated {fpath} ({len(audio_bytes)} bytes)")

if __name__ == "__main__":
    asyncio.run(generate())

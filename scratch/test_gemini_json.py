import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GEMINI_API_KEY")

models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-pro", "gemini-flash-latest"]

system_prompt = """You are a senior quantitative strategist specializing in Indian equity derivatives (NIFTY 50 options).
Analyze the real-time market data: NIFTY 24366, Day change -0.12%, VIX 11.32, Score -30.33 (Mildly Bearish).

Return a valid JSON object with EXACTLY these keys:
{
  "headline": "1-line market headline with emoji prefix",
  "executive_synthesis": "2-3 sentence institutional analysis",
  "sector_flow_narrative": "1-2 sentences on sector rotation",
  "macro_risk_narrative": "1-2 sentences on global macro risk factors",
  "options_bias": "BUY NIFTY PE (Puts)",
  "options_confidence": "MODERATE",
  "options_recommended_strike": "24350 PE",
  "options_atm_strike": 24350,
  "options_itm_strike": 24400,
  "options_profit_target": "24300 - 24250 spot target",
  "options_stop_loss": "Invalidate if score rises above -15.0 or price reclaims 24400",
  "options_iv_regime": "INDIA VIX low at 11.32 (Low IV environment)",
  "key_bullets": ["bullet 1", "bullet 2", "bullet 3", "bullet 4"]
}
Return raw JSON only."""

payload = {
    "contents": [{"parts": [{"text": system_prompt}]}],
    "generationConfig": {
        "temperature": 0.2,
        "maxOutputTokens": 800,
        "responseMimeType": "application/json",
    }
}

for m in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            txt = data['candidates'][0]['content']['parts'][0]['text']
            print(f"SUCCESS with model '{m}':")
            print("RAW TEXT:\n", txt)
            parsed = json.loads(txt)
            print("\nPARSED KEYS:", list(parsed.keys()))
            print("PLAYBOOK BIAS:", parsed['options_bias'])
            print("RECOMMENDED STRIKE:", parsed['options_recommended_strike'])
            break
    except Exception as e:
        print(f"Model '{m}' failed: {e}")

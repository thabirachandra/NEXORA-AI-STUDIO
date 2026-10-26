import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS = ["script", "title", "shorts", "seo", "thumbnail", "chapters", "audit"]

SYSTEM_PROMPT = """
You are NEXORA AI STUDIO, a helpful YouTube creator assistant.
Create useful, original, well-structured content for the selected tool.
Respect the requested language and style.
Do not invent facts, sources, analytics, or timestamps.
Clearly label suggestions that require verification.
Use clear headings and practical output.
"""

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json(200, {"status": "ok"})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self.send_json(200, {"status": "ok"})
        elif path == "/":
            self.send_json(200, {
                "name": "NEXORA AI STUDIO",
                "status": "running",
                "provider": "Google Gemini",
                "tools": TOOLS
            })
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/generate":
            self.send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid JSON"})
            return

        tool = data.get("tool", "")
        topic = data.get("topic", "")
        language = data.get("language", "Hindi / Hinglish")
        audience = data.get("audience", "YouTube viewers")

        if tool not in TOOLS:
            self.send_json(400, {"error": "Unknown tool"})
            return
        if not isinstance(topic, str) or len(topic.strip()) < 2:
            self.send_json(400, {"error": "Please enter a topic"})
            return

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            key_path = os.path.expanduser("~/.config/nexora/gemini_api_key")
            try:
                with open(key_path, "r", encoding="utf-8") as key_file:
                    api_key = key_file.read().strip()
            except OSError:
                api_key = ""

        if not api_key:
            self.send_json(503, {"error": "Gemini API key is not configured"})
            return

        model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Tool: {tool}\n"
            f"Topic or source text: {topic.strip()}\n"
            f"Language: {language}\n"
            f"Audience: {audience}\n\n"
            "Generate the requested output. Be specific and useful."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1400, "temperature": 0.7}
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + model + ":generateContent"
        )
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            },
            method="POST"
        )

        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))

            candidates = result.get("candidates", [])
            answer = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                answer = "\n".join(
                    part.get("text", "")
                    for part in parts
                    if isinstance(part, dict) and part.get("text")
                ).strip()

            if not answer:
                self.send_json(502, {"error": "Gemini returned no text. Please try again."})
                return

            self.send_json(200, {
                "result": answer,
                "tool": tool,
                "model": model,
                "provider": "Google Gemini"
            })

        except HTTPError as error:
            try:
                details = json.loads(error.read().decode("utf-8"))
                message = details.get("error", {}).get("message", "Gemini API request failed")
            except Exception:
                message = "Gemini API request failed with HTTP " + str(error.code)

            print("Gemini API error:", error.code, message)
            status = error.code if error.code in (400, 401, 403, 429) else 502
            self.send_json(status, {"error": message[:500]})

        except (URLError, TimeoutError) as error:
            print("Connection error:", str(error))
            self.send_json(502, {
                "error": "Could not reach Gemini. Check internet and try again."
            })

        except Exception as error:
            print("Backend error:", type(error).__name__, str(error))
            self.send_json(500, {"error": "Unexpected backend error"})

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"NEXORA AI STUDIO backend listening on port {port}")
    print("Google Gemini integration enabled. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()

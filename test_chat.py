import urllib.request
import json
import time
import sys

def main():
    url = 'http://127.0.0.1:8000/v1/chat/completions'
    
    try:
        prompt = input("Enter your message (or press Enter for 'Hello!'): ").strip()
    except (EOFError, KeyboardInterrupt):
        prompt = ""
        
    if not prompt:
        prompt = "Hello! Who are you?"

    print(f"\nSending: '{prompt}'...")
    payload = {
        'model': 'olmoe-colibri',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 30,
        'temperature': 0.7,
        'stream': True
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    t0 = time.time()
    print("\nAssistant: ", end="", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for line in resp:
                line = line.decode('utf-8').strip()
                if line.startswith('data:') and not line.endswith('[DONE]'):
                    try:
                        chunk = json.loads(line[5:].strip())
                        delta = chunk['choices'][0]['delta'].get('content', '')
                        print(delta, end="", flush=True)
                    except Exception:
                        pass
        print(f"\n\n[Completed in {time.time() - t0:.2f} seconds]")
    except Exception as e:
        print(f"\n[Error connecting to Colibri server]: {e}")
        print("Make sure START_COLIBRI.bat is running!")

if __name__ == "__main__":
    main()

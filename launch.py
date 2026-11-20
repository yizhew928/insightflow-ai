"""Start the project-owned model and dashboard on loopback. Ctrl-C stops both."""
import argparse
import http.client
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
# Prefer a private install; reuse the verified V2 weights on the prepared Mac.
RUNTIME = ROOT / '.runtime'
if not (RUNTIME / 'llama-b12563' / 'llama-server').is_file():
    RUNTIME = ROOT.parent / 'InsightFlow-AI-V2' / '.runtime'
BINARY = RUNTIME / 'llama-b12563' / 'llama-server'
WEIGHTS = RUNTIME / 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf'
MODEL_PORT, APP_PORT = 18089, 8513
MODEL_NAME = 'insightflow-qwen2.5-7b'
URL = f'http://127.0.0.1:{APP_PORT}'


def get(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
    try:
        conn.request('GET', path)
        response = conn.getresponse()
        return response.read(65536) if response.status == 200 else b''
    except OSError:
        return b''
    finally:
        conn.close()


def wait_ready(process, port, path):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(f'Service exited with code {process.returncode}. See the terminal or model.log.')
        if get(port, path):
            return
        time.sleep(.5)
    raise RuntimeError(f'Local service at port {port} took too long to start.')


def main(open_browser):
    children = []
    try:
        if BINARY.is_file() and WEIGHTS.is_file():
            listing = get(MODEL_PORT, '/v1/models')
            if listing:
                ids = [m['id'] for m in json.loads(listing)['data']]
                if MODEL_NAME not in ids:
                    raise RuntimeError(f'Port {MODEL_PORT} is occupied by a different model.')
            else:
                (ROOT / 'run').mkdir(exist_ok=True)
                with (ROOT / 'run' / 'model.log').open('w') as log:
                    model = subprocess.Popen([str(BINARY), '-m', str(WEIGHTS), '--alias', MODEL_NAME,
                        '--offline', '--no-ui', '--no-agent', '--host', '127.0.0.1',
                        '--port', str(MODEL_PORT), '-c', '4096', '-np', '1', '-t', '4',
                        '--log-disable'], cwd=ROOT, stdout=log, stderr=log)
                children.append(model)
                wait_ready(model, MODEL_PORT, '/health')
        else:
            print('Local model files are unavailable. The dashboard can run in Local rules mode.', flush=True)
        if get(APP_PORT, '/_stcore/health'):
            print(f'An application already uses {URL}. Use the already-running V3 session if it is yours.', flush=True)
            if open_browser:
                webbrowser.open(URL)
            return
        app = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'app.py',
                                '--server.address', '127.0.0.1', '--server.port', str(APP_PORT)], cwd=ROOT)
        children.append(app)
        wait_ready(app, APP_PORT, '/_stcore/health')
        print(f'InsightFlow AI V3: {URL}', flush=True)
        if open_browser:
            webbrowser.open(URL)
        if app.wait():
            raise RuntimeError('The dashboard stopped unexpectedly.')
    finally:
        for proc in reversed(children):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true', help='Open the dashboard in the default browser')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        main(args.open)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError) as err:
        sys.exit(str(err))

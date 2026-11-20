import os, tarfile, requests, json, time

src_dir = r'C:\Users\vajja\saarthi'
tar_path = os.path.join(os.environ.get('TEMP', r'C:\Temp'), 'saarthi.tar.gz')
exclude_dirs = {'.git', '.pytest_cache', 'venv', '.venv', '__pycache__', 'node_modules', 'dist', '.next'}
exclude_exts = {'.db', '.pyc'}
exclude_files = {'.env', '.env.local'}

print("Packaging project for Embarko...")
with tarfile.open(tar_path, 'w:gz') as tar:
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        for f in files:
            if any(f.endswith(ext) for ext in exclude_exts):
                continue
            if f in exclude_files or f.startswith('.env'):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, src_dir)
            arcname = rel_path.replace('\\', '/')
            tar.add(full_path, arcname=arcname)

print(f"Archive ready: {tar_path} ({os.path.getsize(tar_path)} bytes)")

cred_path = os.path.expanduser('~/.embarko/credentials')
with open(cred_path, 'r', encoding='utf-8') as f:
    token = f.read().strip()

headers = {
    'Authorization': f'Bearer {token}',
    'X-App-Name': 'saarthi',
    'X-Agent-Name': 'antigravity'
}

with open(tar_path, 'rb') as f:
    files = {'source': ('saarthi.tar.gz', f, 'application/gzip')}
    resp = requests.post('https://ship.embarko.ai/apps', headers=headers, files=files)
    print('Deploy response status:', resp.status_code)
    print('Deploy response body:', resp.text)
    data = resp.json()

status_url = data.get('links', {}).get('status', 'https://ship.embarko.ai/apps/saarthi/status')
print(f"Polling {status_url}...")

status_headers = {'Authorization': f'Bearer {token}'}

for i in range(15):
    time.sleep(5)
    try:
        res = requests.get(status_url, headers=status_headers)
        res_data = res.json()
        status = res_data.get('status')
        print(f"Poll {i+1}: status = {status}")
        if status == 'live':
            print("SUCCESS! EMBARKO DEPLOYMENT IS LIVE!")
            print("URL:", res_data.get('url', 'https://saarthi.embarko.app'))
            break
        elif status in ('failed', 'crashed'):
            print("Embarko deployment failed:", res_data)
            break
    except Exception as e:
        print("Polling error:", e)

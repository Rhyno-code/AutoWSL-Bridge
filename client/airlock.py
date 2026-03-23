import os
import httpx
import sys
from rich.console import Console
from rich.table import Table
from pathlib import Path

# Setup system path for absolute module imports within the project
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from common.security import Vault

# --- Initialization ---
console = Console()
VAULT = Vault()
TOKEN = VAULT.get_token() # Fetch token from config for authentication

def get_host_ip():
    """
    Identifies the Windows host IP from within a WSL environment.
    Checks /etc/resolv.conf where WSL typically stores the nameserver of the host.
    """
    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if 'nameserver' in line:
                    return line.split()[1]
    # Fallback to localhost if file is missing or IP not found
    return '127.0.0.1'

# API connection settings
HOST_IP = get_host_ip()
BASE_URL = f'http://{HOST_IP}:9000'
HEADERS = {"X-Bridge-Token": TOKEN}

def check_status():
    """Fetches the status of the AutoWSL-Bridge host API."""
    try:
        response = httpx.get(f'{BASE_URL}/status', headers=HEADERS)
        if response.status_code == 200:
            console.print(f'[bold green]Status:[/bold green] {response.json()}')
        else:
            console.print(f'[bold red]Error ({response.status_code}):[/bold red] {response.json().get("detail", "Unauthorized")}')
    except Exception as e:
        console.print(f'[bold red]Error connecting to host bridge:[/bold red] {e}')

def ls(path: str):
    """
    Lists the contents of a specified Windows directory via the bridge.
    Renders the result in a rich CLI table.
    """
    try:
        response = httpx.get(f'{BASE_URL}/ls', params={'path': path}, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            table = Table(title=f"Host Contents of: {data['path']}")
            table.add_column('Filename/Folder', style='cyan')
            for item in data['items']:
                table.add_row(item)
            console.print(table)
        else:
            console.print(f"[bold red]Error ({response.status_code}):[/bold red] {response.json().get('detail', 'Unauthorized')}")
    except Exception as e:
        console.print(f'[bold red]Network Error during LS:[/bold red] {e}')

def pull(win_path: str, local_path: str = '.'):
    """
    Downloads a file from the Windows host to the local WSL filesystem.
    :param win_path: Full Windows path of the source file.
    :param local_path: Local WSL directory to save the file.
    """
    try:
        with httpx.stream('GET', f'{BASE_URL}/pull', params={'path': win_path}, headers=HEADERS) as response:
            if response.status_code == 200:
                filename = os.path.basename(win_path)
                dest = os.path.join(local_path, filename)
                # Stream binary content to local file
                with open(dest, 'wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                console.print(f'[bold green]Successfully pulled file:[/bold green] {filename}')
            else:
                console.print(f'[bold red]Pull Error ({response.status_code})[/bold red]')
    except Exception as e:
        console.print(f'[bold red]Network Error during Pull:[/bold red] {e}')

def push(local_path: str, win_target_path: str):
    """
    Uploads a file from WSL to a whitelisted Windows directory on the host.
    :param local_path: Path to the local file in WSL.
    :param win_target_path: Destination Windows directory path.
    """
    if not os.path.isfile(local_path):
        console.print(f'[bold red]Error:[/bold red] Local WSL file not found: {local_path}')
        return

    try:
        with open(local_path, "rb") as f:
            filename = os.path.basename(local_path)
            # Send file as multipart form-data
            files = {'file': (filename, f)}
            response = httpx.post(
                f'{BASE_URL}/push', 
                params={'path': win_target_path},
                files=files,
                headers=HEADERS
            )
            
            if response.status_code == 200:
                console.print(f'[bold green]Successfully pushed:[/bold green] {filename} to {win_target_path}')
            else:
                console.print(f"[bold red]Push Error ({response.status_code}):[/bold red] {response.json().get('detail', 'Unauthorized')}")
    except Exception as e:
        console.print(f'[bold red]Network Error during Push:[/bold red] {e}')

def clipboard_get():
    """Retrieves and prints the Windows host clipboard content."""
    try:
        response = httpx.get(f'{BASE_URL}/clipboard/get', headers=HEADERS)
        if response.status_code == 200:
            content = response.json()['content']
            console.print(f'[bold blue]Windows Clipboard Content:[/bold blue]\n{content}')
        else:
            console.print(f"[bold red]Clipboard Fetch Error ({response.status_code}):[/bold red] {response.json().get('detail', 'Unauthorized')}")
    except Exception as e:
        console.print(f'[bold red]Network Error fetching clipboard:[/bold red] {e}')

def clipboard_set(content: str):
    """Sets the Windows host clipboard to the specified text."""
    try:
        response = httpx.post(
            f'{BASE_URL}/clipboard/set', 
            params={'content': content},
            headers=HEADERS
        )
        if response.status_code == 200:
            console.print('[bold green]Windows Clipboard successfully updated![/bold green]')
        else:
            console.print(f"[bold red]Clipboard Update Error ({response.status_code}):[/bold red] {response.json().get('detail', 'Unauthorized')}")
    except Exception as e:
        console.print(f'[bold red]Network Error updating clipboard:[/bold red] {e}')

# --- Command Router ---
if __name__ == '__main__':
    if len(sys.argv) < 2:
        console.print('[bold yellow]Usage:[/bold yellow] python airlock.py [status|ls|pull|push|clip-get|clip-set] [args]')
        sys.exit(1)

    cmd = sys.argv[1]
    
    # Simple CLI routing based on command argument
    if cmd == 'status':
        check_status()
    elif cmd == 'ls' and len(sys.argv) > 2:
        ls(sys.argv[2])
    elif cmd == 'pull' and len(sys.argv) > 2:
        pull(sys.argv[2])
    elif cmd == 'push' and len(sys.argv) > 3:
        push(sys.argv[2], sys.argv[3])
    elif cmd == 'clip-get':
        clipboard_get()
    elif cmd == 'clip-set' and len(sys.argv) > 2:
        # Join all arguments after command as the clipboard string
        clipboard_set(" ".join(sys.argv[2:]))
    else:
        console.print(f'[bold red]Unknown Command or Missing Arguments:[/bold red] {cmd}')

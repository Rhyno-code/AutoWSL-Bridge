
import os
import httpx
import sys
import shutil
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.prompt import Prompt, IntPrompt
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

# --- Timeline Design ---
class Timeline:
    """Renders a modern, pulse-style execution timeline."""
    def __init__(self):
        self.events = []
        
    def log(self, symbol, activity, status="DONE", color="cyan", status_color="green"):
        time_str = datetime.now().strftime("%H:%M:%S")
        self.events.append({
            "time": time_str,
            "symbol": symbol,
            "activity": activity,
            "status": status,
            "color": color,
            "status_color": status_color
        })

    def render(self):
        text = Text()
        text.append("  TIME      ACTIVITY FEED                                  STATUS\n", style="bold white")
        text.append("  ━━━━      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   ━━━━━━\n", style="dim")
        
        for i, event in enumerate(self.events):
            is_last = (i == len(self.events) - 1)
            
            # Time
            text.append(f"  {event['time']}  ", style="dim")
            
            # Symbol
            text.append(f"{event['symbol']}  ", style=event['color'])
            
            # Activity
            activity = event['activity'][:45].ljust(45)
            text.append(activity, style="white")
            
            # Status
            text.append(f"[{event['status']}]", style=f"bold {event['status_color']}")
            text.append("\n")
            
            # Pulse line
            if not is_last:
                text.append("            ┃\n", style="dim")
            else:
                text.append("            ▼\n", style="dim")
        
        return text

def get_host_ip():
    """Identifies the Windows host IP from within a WSL environment or uses an override."""
    if os.environ.get('AUTO_WSL_HOST'):
        return os.environ.get('AUTO_WSL_HOST')
    
    # 1. Try to find the default gateway from 'ip route' (Very reliable in WSL2)
    try:
        import subprocess
        result = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if 'via' in line:
                return line.split('via')[1].strip().split()[0]
    except Exception:
        pass

    # 2. Try to find the nameserver (standard WSL gateway fallback)
    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if 'nameserver' in line:
                    ip = line.split()[1]
                    if ip not in ['127.0.0.53', '127.0.0.1']:
                        return ip
    # Fallback to '127.0.0.1' (handles Mirrored Networking)
    return '127.0.0.1'

# API connection settings
HOST_IP = get_host_ip()
BASE_URL = f'http://{HOST_IP}:9000'
HEADERS = {"X-Bridge-Token": TOKEN}

def check_status(silent=False, timeline=None):
    """Fetches the status of the AutoWSL-Bridge host API."""
    if timeline:
        timeline.log("⚙", f"Connecting to {BASE_URL}...", "WAIT", color="yellow", status_color="yellow")
    try:
        response = httpx.get(f'{BASE_URL}/status', headers=HEADERS, timeout=5.0)
        if response.status_code == 200:
            if timeline:
                timeline.log("✔", "Host connection established", "PASS", color="green", status_color="green")
            elif not silent:
                console.print(f'[bold green]Status:[/bold green] {response.json()}')
            return True
        else:
            err = f"Error {response.status_code}"
            if timeline: timeline.log("✖", f"Host rejected connection: {err}", "FAIL", color="red", status_color="red")
            else: console.print(f'[bold red]{err}:[/bold red] {response.json().get("detail", "Unauthorized")}')
    except Exception as e:
        if timeline: timeline.log("✖", f"Connection failed: {str(e)[:30]}", "FAIL", color="red", status_color="red")
        else: console.print(f'[bold red]Error connecting to host bridge:[/bold red] {e}')
    return False

def ls(path: str, timeline=None):
    """Lists the contents of a specified Windows directory via the bridge."""
    if timeline:
        timeline.log("◈", f"Listing: {path}", "WORK", color="blue", status_color="yellow")
    try:
        response = httpx.get(f'{BASE_URL}/ls', params={'path': path}, headers=HEADERS)
        if response.status_code == 200:
            items = response.json()['items']
            if timeline: timeline.log("✔", f"Found {len(items)} items", "DONE", color="green", status_color="green")
            return items
        else:
            if timeline: timeline.log("✖", f"Failed to list directory", "FAIL", color="red", status_color="red")
    except Exception as e:
        if timeline: timeline.log("✖", "Network Error during LS", "FAIL", color="red", status_color="red")
    return []

def pull(win_path: str, local_path: str = '.', timeline=None):
    """Downloads a file from the Windows host to the local WSL filesystem."""
    filename = os.path.basename(win_path)
    if timeline:
        timeline.log("⚙", f"Pulling: {filename}", "WAIT", color="magenta", status_color="yellow")
    try:
        with httpx.stream('GET', f'{BASE_URL}/pull', params={'path': win_path}, headers=HEADERS) as response:
            if response.status_code == 200:
                dest = os.path.join(local_path, filename)
                with open(dest, 'wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                if timeline: timeline.log("✔", f"Saved to {local_path}", "DONE", color="green", status_color="green")
                else: console.print(f'[bold green]Successfully pulled file:[/bold green] {filename}')
            else:
                if timeline: timeline.log("✖", "Pull failed (Unauthorized/Missing)", "FAIL", color="red", status_color="red")
    except Exception as e:
        if timeline: timeline.log("✖", f"Network Error: {str(e)[:20]}", "FAIL", color="red", status_color="red")

def push(local_path: str, win_target_path: str, timeline=None):
    """Sends a local file from WSL to a whitelisted Windows directory."""
    if not os.path.isfile(local_path):
        if timeline: timeline.log("✖", f"Local file not found: {local_path}", "FAIL", color="red", status_color="red")
        return

    filename = os.path.basename(local_path)
    if timeline: timeline.log("⚙", f"Pushing: {filename}", "WAIT", color="magenta", status_color="yellow")
    try:
        with open(local_path, "rb") as f:
            files = {'file': (filename, f)}
            response = httpx.post(f'{BASE_URL}/push', params={'path': win_target_path}, files=files, headers=HEADERS)
            
            if response.status_code == 200:
                if timeline: timeline.log("✔", f"Pushed to {win_target_path}", "DONE", color="green", status_color="green")
            else:
                if timeline: timeline.log("✖", f"Push failed: {response.status_code}", "FAIL", color="red", status_color="red")
    except Exception as e:
        if timeline: timeline.log("✖", f"Network Error: {str(e)[:20]}", "FAIL", color="red", status_color="red")

def clipboard_get(timeline=None):
    """Retrieves text from the Windows clipboard."""
    if timeline: timeline.log("◈", "Reading Windows Clipboard...", "WORK", color="blue", status_color="yellow")
    try:
        response = httpx.get(f'{BASE_URL}/clipboard/get', headers=HEADERS)
        if response.status_code == 200:
            content = response.json()['content']
            if timeline: timeline.log("✔", f"Retrieved {len(content)} chars", "DONE", color="green", status_color="green")
            return content
        else:
            if timeline: timeline.log("✖", "Clipboard read failed", "FAIL", color="red", status_color="red")
    except Exception as e:
        if timeline: timeline.log("✖", "Network Error during clip-get", "FAIL", color="red", status_color="red")
    return None

def clipboard_set(content: str, timeline=None):
    """Sets the Windows clipboard content."""
    if timeline: timeline.log("⚙", "Updating Windows Clipboard...", "WAIT", color="magenta", status_color="yellow")
    try:
        response = httpx.post(f'{BASE_URL}/clipboard/set', params={'content': content}, headers=HEADERS)
        if response.status_code == 200:
            if timeline: timeline.log("✔", "Clipboard updated", "DONE", color="green", status_color="green")
        else:
            if timeline: timeline.log("✖", "Clipboard update failed", "FAIL", color="red", status_color="red")
    except Exception as e:
        if timeline: timeline.log("✖", "Network Error during clip-set", "FAIL", color="red", status_color="red")

def interactive_mode():
    """Interactive loop for browsing the Vault and performing actions."""
    w = shutil.get_terminal_size().columns - 2
    console.print(f"\n\033[38;2;142;117;255m┏━ AutoWSL Airlock {'━' * (w - 18)}┓")
    console.print(f"┃  [bold white]Timeline-Enabled Interactive Client[/bold white] {' ' * (w - 36)}┃")
    console.print(f"┗{'━' * w}┛\033[0m\n")

    timeline = Timeline()
    with Live(timeline.render(), refresh_per_second=4) as live:
        if not check_status(silent=True, timeline=timeline):
            live.update(timeline.render())
            console.print("\n[bold red]Host unreachable. Start host/main.py on Windows first.[/bold red]")
            return
        live.update(timeline.render())

    # Start at the Vault roots
    vault_roots = VAULT.config['vault']
    current_path = None
    
    while True:
        if current_path is None:
            table = Table(title="Available Vault Roots", show_header=True, header_style="bold cyan")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Windows Path", style="green")
            for idx, root in enumerate(vault_roots):
                table.add_row(str(idx + 1), root)
            console.print(table)
            
            choice = Prompt.ask("Select a root (or 'q' to quit)", choices=[str(i+1) for i in range(len(vault_roots))] + ['q', 'c'])
            if choice == 'q': break
            if choice == 'c':
                content = clipboard_get(timeline=Timeline())
                if content: console.print(Panel(content, title="Windows Clipboard"))
                continue
            current_path = vault_roots[int(choice) - 1]
        else:
            items = ls(current_path)
            table = Table(title=f"Browsing: {current_path}", show_header=True, header_style="bold cyan")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Name", style="yellow")
            
            table.add_row("0", ".. (Back)")
            for idx, item in enumerate(items):
                table.add_row(str(idx + 1), item)
            console.print(table)
            
            max_val = len(items)
            choice = Prompt.ask(f"Select item (0-{max_val}), 'q' to reset, or 'c' for clipboard", default="0")
            
            if choice == 'q':
                current_path = None
                continue
            if choice == 'c':
                content = clipboard_get(timeline=Timeline())
                if content: console.print(Panel(content, title="Windows Clipboard"))
                continue
            
            try:
                idx = int(choice)
                if idx == 0:
                    parent = os.path.dirname(current_path.rstrip('\\'))
                    if any(current_path.startswith(root) and len(current_path) > len(root) for root in vault_roots):
                        current_path = parent
                    else:
                        current_path = None
                elif 1 <= idx <= max_val:
                    selected = items[idx-1]
                    new_path = os.path.join(current_path, selected)
                    
                    # Try to LS it to see if it's a dir
                    test_items = ls(new_path)
                    if test_items:
                        current_path = new_path
                    else:
                        action = Prompt.ask(f"Action for '{selected}'", choices=["pull", "back", "cancel"], default="pull")
                        if action == "pull":
                            t = Timeline()
                            with Live(t.render(), refresh_per_second=4) as live:
                                pull(new_path, timeline=t)
                                live.update(t.render())
            except ValueError:
                console.print("[red]Invalid selection.[/red]")

# --- Command Router ---
if __name__ == '__main__':
    if len(sys.argv) < 2:
        interactive_mode()
        sys.exit(0)

    cmd = sys.argv[1]
    t = Timeline()
    
    with Live(t.render(), refresh_per_second=4) as live:
        if cmd == 'status':
            check_status(timeline=t)
        elif cmd == 'ls' and len(sys.argv) > 2:
            ls(sys.argv[2], timeline=t)
        elif cmd == 'pull' and len(sys.argv) > 2:
            pull(sys.argv[2], timeline=t)
        elif cmd == 'push' and len(sys.argv) > 3:
            push(sys.argv[2], sys.argv[3], timeline=t)
        elif cmd == 'clip-get':
            content = clipboard_get(timeline=t)
            if content: live.stop(); console.print(Panel(content, title="Windows Clipboard"))
        elif cmd == 'clip-set' and len(sys.argv) > 2:
            clipboard_set(" ".join(sys.argv[2:]), timeline=t)
        else:
            t.log("✖", f"Unknown command: {cmd}", "ERROR", color="red", status_color="red")
        live.update(t.render())


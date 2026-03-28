import os
import httpx
import sys
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.live import Live
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

# --- Platform-aware key reading ---
def _read_key():
    """Reads a single keypress, handling arrow keys. Returns a string identifier."""
    if sys.platform == 'win32':
        import msvcrt
        key = msvcrt.getwch()
        if key in ('\x00', '\xe0'):  # Special key prefix on Windows
            key2 = msvcrt.getwch()
            if key2 == 'H': return 'up'
            if key2 == 'P': return 'down'
            return None
        if key == '\r': return 'enter'
        return key
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': return 'up'
                    if ch3 == 'B': return 'down'
                return None
            if ch in ('\r', '\n'): return 'enter'
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def menu_select(title: str, options: list[str], hint: str = "↑/↓ navigate  Enter select  q quit") -> int | None:
    """
    Interactive arrow-key menu, gemini-cli style.

    Returns the selected index (0-based), or None if the user pressed 'q'.
    """
    selected = 0
    total = len(options)

    def _render():
        lines = Text()
        lines.append(f"  {title}\n", style="bold cyan")
        lines.append(f"  {hint}\n\n", style="dim")
        for i, opt in enumerate(options):
            if i == selected:
                lines.append("  ❯ ", style="bold cyan")
                lines.append(f"{opt}\n", style="bold white")
            else:
                lines.append("    ", style="dim")
                lines.append(f"{opt}\n", style="dim white")
        return Panel(lines, border_style="bright_cyan", expand=False, padding=(0, 1))

    with Live(_render(), console=console, refresh_per_second=30, transient=True) as live:
        while True:
            key = _read_key()
            if key == 'up':
                selected = (selected - 1) % total
            elif key == 'down':
                selected = (selected + 1) % total
            elif key == 'enter':
                # Print the final selection so it stays on screen
                console.print(f"  [bold cyan]❯[/bold cyan] [bold]{options[selected]}[/bold]")
                return selected
            elif key == 'q':
                return None
            live.update(_render())


def get_host_ip():
    """Identifies the Windows host IP from within a WSL environment."""
    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if 'nameserver' in line:
                    return line.split()[1]
    return '127.0.0.1'

# API connection settings
HOST_IP = get_host_ip()
BASE_URL = f'http://{HOST_IP}:9000'
HEADERS = {"X-Bridge-Token": TOKEN}

def discover_host(port_range=(9000, 9999)):
    """Scans for the bridge host across a range of ports using fast socket checks."""
    global BASE_URL
    console.print(f"[bold blue]Scanning for host at {HOST_IP} on ports {port_range[0]}-{port_range[1]}...[/bold blue]")
    
    def try_port(port):
        # Quick socket check first to see if port is even open
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex((HOST_IP, port)) == 0:
                    # Port is open, now try the actual API
                    url = f'http://{HOST_IP}:{port}'
                    with httpx.Client(timeout=1.0) as client:
                        response = client.get(f'{url}/status', headers=HEADERS)
                        if response.status_code == 200:
                            return url
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(try_port, port) for port in range(port_range[0], port_range[1] + 1)]
        for future in as_completed(futures):
            found_url = future.result()
            if found_url:
                BASE_URL = found_url
                console.print(f"[bold green]Host discovered at {BASE_URL}[/bold green]")
                return True
    
    return False

def check_status(silent=False):
    """Fetches the status of the AutoWSL-Bridge host API."""
    try:
        response = httpx.get(f'{BASE_URL}/status', headers=HEADERS, timeout=2.0)
        if response.status_code == 200:
            if not silent:
                console.print(f'[bold green]Status:[/bold green] {response.json()}')
            return True
        else:
            if not silent:
                console.print(f'[bold red]Error ({response.status_code}):[/bold red] {response.json().get("detail", "Unauthorized")}')
    except Exception as e:
        if not silent:
            console.print(f'[bold red]Error connecting to host bridge:[/bold red] {e}')
    return False

def ls(path: str):
    """Lists the contents of a specified Windows directory via the bridge."""
    try:
        response = httpx.get(f'{BASE_URL}/ls', params={'path': path}, headers=HEADERS, timeout=5.0)
        if response.status_code == 200:
            return response.json()['items']
        else:
            console.print(f"[bold red]Error ({response.status_code}):[/bold red] {response.json().get('detail', 'Unauthorized')}")
    except Exception as e:
        console.print(f'[bold red]Network Error during LS:[/bold red] {e}')
    return []

def pull(win_path: str, local_path: str = '.'):
    """Downloads a file from the Windows host to the local WSL filesystem."""
    try:
        with httpx.stream('GET', f'{BASE_URL}/pull', params={'path': win_path}, headers=HEADERS, timeout=None) as response:
            if response.status_code == 200:
                filename = os.path.basename(win_path)
                dest = os.path.join(local_path, filename)
                with open(dest, 'wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                console.print(f'[bold green]Successfully pulled file:[/bold green] {filename}')
            else:
                console.print(f'[bold red]Pull Error ({response.status_code})[/bold red]')
    except Exception as e:
        console.print(f'[bold red]Network Error during Pull:[/bold red] {e}')

def interactive_mode():
    """Interactive loop for browsing the Vault and performing actions."""
    # Ensure host is found before starting
    if not check_status(silent=True):
        if not discover_host():
            console.print("[bold red]Host unreachable. Start host/main.py on Windows first.[/bold red]")
            return

    w = shutil.get_terminal_size().columns - 2
    console.print(f"\n\033[38;2;0;255;255m╭─ AutoWSL Airlock Interactive {'─' * (w - 30)}╮")
    console.print(f"\033[38;2;85;225;170m│  Connected to: {BASE_URL} {' ' * (w - len(BASE_URL) - 17)}│")
    console.print(f"\033[38;2;255;165;0m╰{'─' * w}╯\033[0m\n")

    # Start at the Vault roots
    vault_roots = VAULT.config.get('vault', [])
    if not vault_roots:
        console.print("[bold red]No Vault roots configured in config.yaml[/bold red]")
        return
        
    current_path = None
    
    while True:
        if current_path is None:
            # Show Vault Roots as interactive menu
            choice = menu_select(
                "Available Vault Roots",
                vault_roots,
                hint="↑/↓ navigate  Enter select  q quit"
            )
            if choice is None:
                break
            current_path = vault_roots[choice]
        else:
            # Browse current path as interactive menu
            items = ls(current_path)
            browse_options = ["⮤  .. (Back)"] + items
            extra_hint = "↑/↓ navigate  Enter select  p pull file  q reset"
            
            console.print(f"  [dim]Browsing:[/dim] [bold yellow]{current_path}[/bold yellow]\n")
            choice = menu_select(
                "Directory Contents",
                browse_options,
                hint=extra_hint
            )
            
            if choice is None:
                current_path = None
                continue
            
            if choice == 0:
                # Go back
                parent = os.path.dirname(current_path.rstrip('\\'))
                if any(current_path.startswith(root) and len(current_path) > len(root) for root in vault_roots):
                    current_path = parent
                else:
                    current_path = None
            else:
                selected = items[choice - 1]
                new_path = os.path.join(current_path, selected)
                
                # Try to LS it to see if it's a dir
                test_items = ls(new_path)
                if test_items:
                    current_path = new_path
                else:
                    # Likely a file or empty dir, ask to pull
                    if Prompt.ask(f"Pull '{selected}' to current directory?", choices=["y", "n"], default="y") == "y":
                        pull(new_path)

# --- Command Router ---
if __name__ == '__main__':
    if len(sys.argv) < 2:
        interactive_mode()
        sys.exit(0)

    cmd = sys.argv[1]
    
    # Try discovery if simple check fails
    if not check_status(silent=True):
        discover_host()

    if cmd == 'status':
        check_status()
    elif cmd == 'ls' and len(sys.argv) > 2:
        items = ls(sys.argv[2])
        if items:
            table = Table(title=f"Host Contents of: {sys.argv[2]}")
            table.add_column('Filename/Folder', style='cyan')
            for item in items: table.add_row(item)
            console.print(table)
    elif cmd == 'pull' and len(sys.argv) > 2:
        pull(sys.argv[2])
    elif cmd == 'scan':
        # Explicit scan command
        discover_host(port_range=(0, 65535) if "--all" in sys.argv else (9000, 9100))
    else:
        console.print(f'[bold red]Unknown Command or Missing Arguments:[/bold red] {cmd}')

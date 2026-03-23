# ▗▄▄▖ AutoWSL-Bridge
# ▟█▀▀█▙
# ▟█▙▄▄▟█▙
# ▀▀    ▀▀ ▀▀▀

**AutoWSL-Bridge** is a secure, high-speed bridge between Windows and WSL (Windows Subsystem for Linux), enabling automated cross-environment workflows.

## Features
- **Secure File Access:** Controlled access to Windows directories from WSL.
- **Automated Workflows:** Bridge-integrated client for seamless interaction.
- **Agent Mode:** Interactive AI-assisted command generation.

## Setup
1. **Configure:** Edit `config.yaml` to set your vault directories and security token.
2. **Start Host:**
   ```powershell
   python host/main.py
   ```
3. **Use Client:**
   ```bash
   python client/airlock.py
   ```

## Security
This bridge is designed with security in mind. Ensure you change the default `SECRET_TOKEN_CHANGE_ME` in your `config.yaml` before deploying to a production environment.

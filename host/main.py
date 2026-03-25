from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Depends, Header
from fastapi.responses import FileResponse, StreamingResponse
import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path
import uvicorn

# Ensure the root project directory is in the Python search path for absolute module imports
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from common.security import Vault

# --- Configure Logging ---
# Log to both 'bridge.log' file and console for monitoring activity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bridge.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AutoWSL-Bridge")

# Initialize FastAPI app and Security Vault
app = FastAPI(title='AutoWSL-Bridge Host')
VAULT = Vault()

# --- Security Dependency ---
async def verify_token(x_bridge_token: str = Header(...)):
    """
    Middleware function that checks for the 'X-Bridge-Token' in request headers.
    Ensures that only authorized clients (like the WSL airlock client) can access host data.
    """
    if not VAULT.verify_token(x_bridge_token):
        logger.warning(f"Unauthorized access attempt with token: {x_bridge_token}")
        raise HTTPException(status_code=403, detail="Invalid Security Token")

# --- File Operations Endpoints ---

@app.get('/status', dependencies=[Depends(verify_token)])
def get_status():
    """Returns the current operational status of the host bridge."""
    return {
        'status': 'active', 
        'msg': 'AutoWSL-Bridge is online',
        'read_only': VAULT.is_read_only()
    }

@app.get('/ls', dependencies=[Depends(verify_token)])
def list_files(path: str):
    """
    Lists files in a given Windows directory.
    Validates the path against the Vault's whitelist before listing.
    """
    if not VAULT.is_safe(path):
        logger.warning(f"Access Denied for path listing: {path}")
        raise HTTPException(status_code=403, detail='Access Denied: Path not in Vault')
    
    try:
        items = os.listdir(path)
        logger.info(f"Listed files in directory: {path}")
        return {'path': path, 'items': items}
    except Exception as e:
        logger.error(f"Error listing files in {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/pull', dependencies=[Depends(verify_token)])
def pull_file(path: str):
    """
    Retrieves a single file from the Windows host for the WSL client.
    Ensures the requested file is within a whitelisted directory.
    """
    if not VAULT.is_safe(path):
        logger.warning(f"Access Denied for file pull: {path}")
        raise HTTPException(status_code=403, detail='Access Denied: Path not in Vault')
    
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='File not found')
    
    logger.info(f"File pulled from host: {path}")
    return FileResponse(path)

@app.post('/push', dependencies=[Depends(verify_token)])
async def push_file(path: str, file: UploadFile = File(...)):
    """
    Receives a file upload from WSL and saves it to a specified Windows path.
    Enforces 'read-only' mode and Vault whitelisting before saving.
    """
    if VAULT.is_read_only():
        raise HTTPException(status_code=403, detail='Access Denied: Bridge is in Read-Only mode')
    
    # Path validation for security
    if not VAULT.is_safe(path):
        logger.warning(f"Access Denied for target upload path: {path}")
        raise HTTPException(status_code=403, detail='Access Denied: Target path not in Vault')
    
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail='Target path must be an existing directory')

    try:
        dest_path = os.path.join(path, file.filename)
        # Write the file stream chunk-by-chunk to the disk
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"File pushed to host: {file.filename} saved to {path}")
        return {"filename": file.filename, "msg": "Successfully pushed"}
    except Exception as e:
        logger.error(f"Error pushing file {file.filename} to {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Clipboard Integration Endpoints ---

@app.get('/clipboard/get', dependencies=[Depends(verify_token)])
def get_clipboard():
    """
    Retrieves the current text content from the Windows host system clipboard.
    Uses PowerShell's 'Get-Clipboard' command to bridge environments.
    """
    try:
        # Run powershell command in a clean profile to fetch clipboard content
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, check=True
        )
        content = result.stdout.strip()
        logger.info("Windows clipboard content retrieved successfully")
        return {"content": content}
    except Exception as e:
        logger.error(f"Error reading Windows clipboard: {e}")
        raise HTTPException(status_code=500, detail="Could not read Windows clipboard")

@app.post('/clipboard/set', dependencies=[Depends(verify_token)])
def set_clipboard(content: str):
    """
    Sets the Windows host system clipboard to the provided string.
    Employs PowerShell's 'Set-Clipboard' via subprocess.
    """
    try:
        # Execute powershell to update the clipboard value securely
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "Set-Clipboard", "-Value", f'"{content}"'],
            check=True
        )
        
        # Log a snippet of the clipboard content for audit tracking
        snippet = content[:20] + "..." if len(content) > 20 else content
        logger.info(f"Windows clipboard content updated: {snippet}")
        return {"msg": "Clipboard updated successfully"}
    except Exception as e:
        logger.error(f"Error setting Windows clipboard: {e}")
        raise HTTPException(status_code=500, detail="Could not set Windows clipboard")

# --- Main Entry Point ---
if __name__ == '__main__':
    logger.info("Starting AutoWSL-Bridge Host API on port 9000...")
    # Bind to 0.0.0.0 to ensure access from the WSL virtual bridge and other interfaces
    uvicorn.run(app, host='0.0.0.0', port=9000)

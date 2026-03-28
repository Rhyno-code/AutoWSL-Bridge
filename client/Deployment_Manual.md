# Deployment Manual: License Manager WebApp

## 1. LAN Deployment (Local Area Network)
This scenario is for deploying the application on a server within a company's internal network, making it accessible to employees via their local IP addresses.

### Prerequisites
- A dedicated server or PC running Windows, Linux, or macOS.
- Python 3.9+ installed. better still the latest version of python
- Node.js 18+ installed.better still the latest version of nodejs
- Git installed.

### Step 1: Backend Setup
1. **Clone the Repository:**
   ```bash
   git clone https://github.com/Rhyno-code/License-Manager-webapp.git
   cd License-Manager-webapp/backend
   ```
   **Mr. Soh in your case you already have the project folder so you just navigate to the backend folder**
   ```bash
   cd webApp/backend
   ```

2. **Create a Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # OR
   venv\Scripts\activate     # Windows
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API Host:**
   By default, FastAPI runs on `127.0.0.1`. To make it accessible on the LAN, you must bind it to `0.0.0.0`.

5. **Start the Backend:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### Step 2: Frontend Setup
1. **Navigate to Frontend Directory:**
   ```bash
   cd ../LicenseApi
   ```

2. **Install Dependencies:**
   ```bash
   npm install
   ```

3. **Configure API URL:**
   Edit `src/api/api.jsx`. Change `const API_URL = 'http://localhost:8000/api';` to the server's local IP address:
   ```javascript
   const API_URL = 'http://192.168.1.10:8000/api'; // Replace with your server's IP
   ```

4. **Build the Frontend:**
   ```bash
   npm run build
   ```

5. **Serve the Frontend:**
   You can use a simple static server like `serve`:
   ```bash
   npm install -g serve
   serve -s dist -l 5173
   ```

### Step 3: Accessing the App
Employees can now access the app via their browsers:
- **URL:** `http://192.168.1.10:5173` (Replace with server IP)

---

## 2. Web Deployment (Public Internet)
This scenario is for deploying the application to a VPS (e.g., DigitalOcean, AWS, Linode) using a domain name and SSL (HTTPS).

### Recommended Stack
- **Web Server:** Nginx (Reverse Proxy)
- **Process Manager:** Gunicorn with Uvicorn workers
- **SSL:** Let's Encrypt (Certbot)

### Step 1: Backend Production Setup
1. **Install Gunicorn:**
   ```bash
   pip install gunicorn
   ```

2. **Run with Gunicorn:**
   ```bash
   gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
   ```

### Step 2: Nginx Configuration
Create an Nginx server block to serve the frontend and proxy API requests.

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Frontend Static Files
    location / {
        root /var/www/license-manager/dist;
        index index.html;
        try_files $uri /index.html;
    }

    # Backend API Proxy
    location /api {
        proxy_pass http://127.0.0.1:8000/api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Static Media Files (Uploads)
    location /static {
        alias /var/www/license-manager/backend/static;
    }
}
```

### Step 3: Database Migration (Optional but Recommended)
For web deployment, SQLite might be slow for many concurrent users.
1. **Install PostgreSQL.**
2. **Update `backend/database.py`:**
   ```python
   DATABASE_URL = "postgresql://user:password@localhost/dbname"
   ```

### Step 4: Security
1. **Enable HTTPS:**
   ```bash
   sudo certbot --nginx -d yourdomain.com
   ```

2. **Update CORS:**
   In `backend/main.py`, update `origins` to include your production domain:
   ```python
   origins = ["https://yourdomain.com"]
   ```

---

## 3. Post-Deployment Checklist
- [ ] **Firewall:** Ensure ports 80 (HTTP), 443 (HTTPS), and 8000 (if exposed) are open.
- [ ] **Persistence:** Use a tool like `systemd` (Linux) or `pm2` to ensure the backend restarts automatically if the server reboots.
- [ ] **Backup:** Schedule regular backups of `database.db` or your production database.
- [ ] **Environment Variables:** Move sensitive data (like `SECRET_KEY` for JWT) to an `.env` file and load it using `python-dotenv`.

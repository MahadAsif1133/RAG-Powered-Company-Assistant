# Deploying the Backend on an Ubuntu EC2 Instance

This guide walks through deploying the **Company Knowledge Assistant** backend (`FastAPI` + `Redis`, with optional `AWS S3` document storage) on an **Ubuntu 22.04 / 24.04 LTS** EC2 instance using Docker Compose and Caddy (automatic HTTPS), while keeping the Next.js frontend hosted on **Vercel** and the database/auth on **Supabase**.

---

## 1. Set Up an AWS Billing Alert First

Before launching any EC2 or S3 resources, set up a billing alarm so there are no surprise charges:

1. In the AWS Console, open **Billing and Cost Management → Budgets → Create budget**.
2. Select **Use a template → Monthly cost budget** (or **Zero spend budget** if staying strictly within Free Tier).
3. Set your monthly threshold (for example, `$5.00`) and enter your email address for notifications.
4. Optionally enable **AWS Cost Anomaly Detection** under **Cost Management**.

---

## 2. Create the S3 Bucket & Least-Privilege IAM Role (Optional S3 Storage)

The backend uses the standard `boto3` AWS credential chain. On EC2, **do not put `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in `.env`** — attach an **IAM Role** directly to the EC2 instance so temporary credentials rotate automatically via IMDSv2.

### 2.1 Create a Private S3 Bucket

1. Open **S3 → Create bucket**.
2. Choose a globally unique name (e.g., `my-company-rag-documents-prod`) and region (e.g., `us-east-1`).
3. Keep **Block all public access** checked (`ON`).
4. Enable **Default encryption** (`SSE-S3` / `AES256`).

All uploaded files are stored under per-tenant prefixes:
```text
s3://<bucket-name>/organizations/<org_id>/<uuid>_<filename>
```

### 2.2 Least-Privilege IAM Policy

Create an IAM Policy (`rag-assistant-s3-policy`) scoped strictly to the `organizations/*` prefix in your bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListBucketOrganizationsPrefixOnly",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "organizations/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadWriteDeleteTenantObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/organizations/*"
    }
  ]
}
```

### 2.3 Attach the IAM Role to EC2

1. Go to **IAM → Roles → Create role**.
2. Trusted entity: **AWS service → EC2**.
3. Attach `rag-assistant-s3-policy` and name the role `rag-assistant-ec2-role`.
4. Attach this role to your EC2 instance (**Actions → Security → Modify IAM role**).

---

## 3. Launch the Ubuntu EC2 Instance

1. **AMI:** Ubuntu Server 24.04 LTS (or 22.04 LTS), `x86_64`.
2. **Instance Type:** `t3.small` or `t3.medium` recommended (2 GB+ RAM for PDF/DOCX parsing). If using a 1 GB `t2.micro`/`t3.micro`, add a 2 GB swapfile before building.
3. **Storage:** 20 GB `gp3` root volume.
4. **Security Group inbound rules:**
   - `22/tcp` (SSH) — restrict to **My IP**
   - `80/tcp` (HTTP, for Let's Encrypt ACME challenge / redirect) — `0.0.0.0/0`
   - `443/tcp` (HTTPS) — `0.0.0.0/0`
   - *(Do **not** expose port `8000` or `6379` publicly; Caddy proxies `443 → 127.0.0.1:8000`.)*

---

## 4. Install Docker & Docker Compose Plugin on Ubuntu

SSH into the instance and install the official Docker Engine and Compose v2 plugin:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow the ubuntu user to run docker without sudo
sudo usermod -aG docker $USER
newgrp docker

docker --version
docker compose version
```

---

## 5. Clone the Repo & Configure Environment Variables

```bash
git clone https://github.com/MahadAsif1133/RAG-Powered-Company-Assistant.git
cd RAG-Powered-Company-Assistant
cp backend/.env.example backend/.env
chmod 600 backend/.env
nano backend/.env
```

Fill in `backend/.env`:

```dotenv
# Supabase
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key

# Embeddings
VOYAGE_API_KEY=your-voyage-api-key
EMBEDDING_DIMENSION=1024

# LLM (Groq)
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=your-chosen-groq-model
LLM_MAX_RETRIES=3

# Ingestion
INGESTION_PIPELINE=llamaindex

# Rate Limiting & Redis Cache
QUERY_RATE_LIMIT=10/minute
MAX_RETRIEVED_CHUNKS=5
REDIS_URL=redis://redis:6379/0
CACHE_TTL_SECONDS=3600

# Storage (set to "s3" to archive uploaded documents to S3, or keep "supabase")
STORAGE_BACKEND=s3
S3_BUCKET_NAME=your-s3-bucket-name
AWS_REGION=us-east-1

# App Config
ENVIRONMENT=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

---

## 6. Run the Docker Compose Stack

```bash
# Validate compose configuration
docker compose config

# Build and start Redis + FastAPI backend in the background
docker compose up --build -d

# Check container status and health
docker compose ps
curl http://127.0.0.1:8000/health
```

Both `redis` and `backend` have `restart: unless-stopped` and healthchecks configured, so they automatically recover after a crash or instance reboot.

---

## 7. Reverse Proxy with HTTPS (Caddy or Nginx)

The Next.js frontend remains deployed on **Vercel** (`https://your-vercel-app.vercel.app`). Because browsers block mixed content (`HTTPS` frontend calling an `HTTP` backend), put **Caddy** (or **Nginx + Certbot**) in front of port `8000` with a DNS `A` record (e.g., `api.yourdomain.com` pointing to your EC2 Elastic IP).

### Option A: Caddy (Recommended — Automatic Let's Encrypt HTTPS)

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
```

Edit `/etc/caddy/Caddyfile`:

```caddyfile
api.yourdomain.com {
    request_body {
        max_size 55MB
    }
    reverse_proxy 127.0.0.1:8000
}
```

Reload Caddy:

```bash
sudo systemctl reload caddy
curl https://api.yourdomain.com/health
```

### Option B: Nginx + Certbot

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/rag-backend`:

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;
    client_max_body_size 55M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and issue a TLS certificate:

```bash
sudo ln -s /etc/nginx/sites-available/rag-backend /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.yourdomain.com
```

Finally, update `NEXT_PUBLIC_BACKEND_URL=https://api.yourdomain.com` in your **Vercel** project settings and redeploy the frontend.

---

## 8. Stopping or Terminating the Instance to Save Costs

- **Stop the containers only:**
  ```bash
  docker compose down
  ```
- **Stop the EC2 instance (stops compute billing; EBS storage (~$1.60/mo for 20 GB) and Elastic IP if unattached still incur small charges):**
  - AWS Console → **EC2 → Instances → Select instance → Instance state → Stop instance**
  - Or via AWS CLI: `aws ec2 stop-instances --instance-ids i-xxxxxxxxxxxxxxxxx`
- **Terminate the EC2 instance (deletes the instance and root EBS volume completely so compute + EBS billing stops):**
  - Release any Elastic IP under **EC2 → Elastic IPs → Release Elastic IP addresses**.
  - AWS Console → **EC2 → Instances → Instance state → Terminate (delete) instance**.

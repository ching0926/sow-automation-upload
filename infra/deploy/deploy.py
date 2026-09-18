"""
Deploy the current local code to the EC2 that terraform provisioned. Re-run any time to redeploy.

Flow (mirrors the backend/ startup command in CLAUDE.md):
  1. Package the repo into a tar.gz (excluding .git / infra / venv / __pycache__ / .env)
  2. Upload it to EC2, replacing /opt/sow-app/app entirely
  3. Separately upload the local root .env (not in git, so not in the tar.gz)
  4. Run `pip install -r backend/requirements.txt` using the venv terraform pre-created
  5. `systemctl restart sow-app` (terraform already wrote the unit: uvicorn app:app --host 0.0.0.0 --port 8000)
  6. Hit /api/cases as a health check; on failure, print journalctl for debugging

Usage:
  pip install -r infra/deploy/requirements.txt
  python infra/deploy/deploy.py
  # By default this reads the EC2 IP / private key path from `terraform output` in infra/terraform.
  # You can also override them and skip the terraform dependency entirely:
  python infra/deploy/deploy.py --host 1.2.3.4 --key infra/terraform/sow-app-deploy-key.pem
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import paramiko

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"

REMOTE_APP_DIR = "/opt/sow-app/app"
REMOTE_VENV_PIP = "/opt/sow-app/venv/bin/pip"
REMOTE_TARBALL = "/tmp/sow-app-deploy.tar.gz"
SERVICE_NAME = "sow-app"

# Paths excluded when packaging (matched against any path component / any depth, relative to repo root)
EXCLUDE_NAMES = {".git", "infra", "__pycache__", "myenv", "venv", ".venv", ".env"}
EXCLUDE_SUFFIXES = {".pyc"}


def log(msg: str) -> None:
    print(f"[deploy] {msg}", flush=True)


def get_terraform_outputs() -> dict:
    try:
        result = subprocess.run(
            ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-json"],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Could not read terraform output (terraform not installed, not applied yet, "
            "or state isn't in infra/terraform). Run `terraform apply` first, or pass "
            "--host / --key to target a machine manually."
        ) from exc
    data = json.loads(result.stdout)
    return {k: v["value"] for k, v in data.items()}


def build_tarball(project_root: Path) -> bytes:
    def excluded(path: Path) -> bool:
        return any(part in EXCLUDE_NAMES for part in path.parts) or path.suffix in EXCLUDE_SUFFIXES

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(project_root.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(project_root)
            if excluded(rel):
                continue
            tar.add(path, arcname=str(rel))
    buf.seek(0)
    return buf.read()


def connect_with_retry(host: str, user: str, key_path: str, attempts: int = 10, delay: int = 6) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = paramiko.RSAKey.from_private_key_file(key_path)
    last_exc: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            client.connect(hostname=host, username=user, pkey=pkey, timeout=10)
            return client
        except Exception as exc:  # noqa: BLE001 - SSH not up yet right after boot is expected, just retry
            last_exc = exc
            log(f"SSH connection failed (attempt {i}/{attempts}, likely still booting): {exc!r}, retrying in {delay}s")
            time.sleep(delay)
    raise RuntimeError(f"SSH connection kept failing: {last_exc!r}")


def run(client: paramiko.SSHClient, command: str) -> str:
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if code != 0:
        raise RuntimeError(f"remote command failed ({code}): {command}\n--- stdout ---\n{out}\n--- stderr ---\n{err}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy sow-automation-upload to the terraform-provisioned EC2")
    parser.add_argument("--host", help="EC2 public IP, defaults to terraform output")
    parser.add_argument("--key", help="SSH private key path, defaults to terraform output")
    parser.add_argument("--user", default="ec2-user")
    parser.add_argument("--port", type=int, default=8000, help="Port uvicorn exposes, used for the post-deploy health check")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"), help="Path to the .env file to upload to the server")
    args = parser.parse_args()

    host, key_path = args.host, args.key
    if not host or not key_path:
        tf_out = get_terraform_outputs()
        host = host or tf_out["public_ip"]
        # terraform's private_key_path output is relative to infra/terraform, not to cwd
        key_path = key_path or str((TERRAFORM_DIR / tf_out["private_key_path"]).resolve())

    env_file = Path(args.env_file)
    if not env_file.exists():
        log(f"Could not find {env_file} -- this deploy will fail (the app can't reach RDS without it).")
        log("Get a .env (DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME) from whoever holds the DB credentials, "
            "place it at the repo root, then re-run.")
        sys.exit(1)

    log(f"Target: {args.user}@{host}")
    log("Packaging local code...")
    tarball = build_tarball(REPO_ROOT)
    log(f"Packaged, size {len(tarball) / 1024:.1f} KB")

    client = connect_with_retry(host, args.user, key_path)
    try:
        sftp = client.open_sftp()
        log("Uploading code...")
        sftp.putfo(io.BytesIO(tarball), REMOTE_TARBALL)
        log("Uploading .env...")
        sftp.put(str(env_file), "/tmp/sow-app.env")
        sftp.close()

        log("Extracting on remote, replacing old code...")
        run(client, f"sudo -n rm -rf {REMOTE_APP_DIR} && sudo -n mkdir -p {REMOTE_APP_DIR}")
        run(client, f"sudo -n tar -xzf {REMOTE_TARBALL} -C {REMOTE_APP_DIR}")
        run(client, f"sudo -n mv /tmp/sow-app.env {REMOTE_APP_DIR}/.env")
        run(client, f"sudo -n chown -R ec2-user:ec2-user {REMOTE_APP_DIR}")

        log("Installing Python packages...")
        run(client, f"{REMOTE_VENV_PIP} install -q -r {REMOTE_APP_DIR}/backend/requirements.txt")

        log("Restarting service...")
        run(client, f"sudo -n systemctl restart {SERVICE_NAME}.service")

        log("Health check...")
        time.sleep(3)
        try:
            run(client, f"curl -sf http://127.0.0.1:{args.port}/api/cases -o /dev/null")
        except RuntimeError:
            log("Health check failed, dumping recent service logs:")
            print(run(client, f"sudo -n journalctl -u {SERVICE_NAME} -n 80 --no-pager"))
            raise

        log(f"Deploy finished: http://{host}:{args.port}/")
    finally:
        client.close()


if __name__ == "__main__":
    main()

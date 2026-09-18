# Deploying to AWS

Two independent layers:

- `terraform/`: builds the "environment" -- EC2, security group, the connectivity rule to the shared RDS, and the systemd unit skeleton. Run once, rarely changes afterwards; `destroy` tears it all down cleanly with nothing left over.
- `deploy/`: pushes "the current code" onto the already-provisioned EC2, installs dependencies, restarts the service. Re-run any time you want to redeploy (e.g. after code changes); it never touches anything terraform manages.

## 1. Create/destroy the environment (terraform)

```powershell
cd infra\terraform
terraform init
terraform plan     # preview what will be created: 7 resources -- EC2, EIP, SG, SG rule, key pair, etc.
terraform apply
```

After `apply` finishes it prints:
- `public_ip` / `app_url`: `deploy.py` reads this automatically afterwards, no need to copy it by hand
- `private_key_path`: the SSH private key generated locally (`sow-app-deploy-key.pem`). It only lives on your machine and is **not** committed to git (already in `.gitignore`)
- `rds_endpoint` / `rds_port`: use these for `.env`'s `DB_HOST`/`DB_PORT`

Don't need this environment anymore:

```powershell
terraform destroy
```

This deletes the EC2/EIP/SG/key pair, and removes that one ingress rule added to the shared RDS's "local" security group -- **it does not touch the RDS itself or any of its other existing security groups/rules**.

> The `intern` profile's credentials are a temporary SSO session token; it needs a fresh login before `apply`/`destroy` will work again once it expires.

## 2. Deploy the current code (python script)

Before the first deploy, put a `.env` at the repo root (`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME`). It's not in git, so you need to add one yourself.

```powershell
pip install -r infra\deploy\requirements.txt
python infra\deploy\deploy.py
```

Every run: packages the local code -> uploads it and replaces `/opt/sow-app/app` on the EC2 entirely -> uploads `.env` -> `pip install -r backend/requirements.txt` into the existing venv -> `systemctl restart sow-app` -> health-checks `/api/cases`. To update after a code change, just re-run this same command.

On failure the script automatically prints the last 80 lines of `journalctl -u sow-app` for debugging; you can also SSH in yourself (`terraform output ssh_command`).

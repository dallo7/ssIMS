# Deploy to AWS ECS Fargate

End-to-end recipe for shipping this app to ECS Fargate with an Application Load
Balancer, Secrets Manager, and a private RDS PostgreSQL.

Works from Windows PowerShell. All AWS commands use the AWS CLI v2.

---

## 0. One-time prerequisites

```powershell
aws --version                        # v2.x
docker --version
aws configure                        # region = eu-north-1 (match your RDS)

$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION     = "eu-north-1"
$REPO       = "cpi-inventory"
$CLUSTER    = "cpi-cluster"
$SERVICE    = "cpi-inventory"
$FAMILY     = "cpi-inventory"
```

---

## 1. Target architecture

```
Internet --> ALB (SG: alb-sg, :80/:443 from 0.0.0.0/0)
                |
                v
           ECS Fargate task (SG: app-sg, :8050 from alb-sg only)
                |
                v
           RDS PostgreSQL (SG: rds-sg, :5432 from app-sg only, not public)
```

- Users reach **ALB** publicly (HTTPS).
- **Only the ALB** can talk to the app container.
- **Only the app** can talk to the database.
- Your laptop never needs direct RDS access in production (use `aws rds` +
  a short-lived bastion / SSM port-forward for admin).

---

## 2. Create the three security groups

Replace `<VPC_ID>` with your VPC (the same VPC as RDS).

```powershell
$VPC_ID = "vpc-xxxxxxxx"

$ALB_SG = (aws ec2 create-security-group --group-name cpi-alb-sg `
  --description "ALB public" --vpc-id $VPC_ID --query GroupId --output text)

$APP_SG = (aws ec2 create-security-group --group-name cpi-app-sg `
  --description "Fargate tasks" --vpc-id $VPC_ID --query GroupId --output text)

$RDS_SG = "sg-xxxxxxxx"   # existing RDS security group id

# ALB: allow 80/443 from the internet
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80  --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

# App: allow 8050 ONLY from the ALB
aws ec2 authorize-security-group-ingress --group-id $APP_SG --protocol tcp --port 8050 --source-group $ALB_SG

# RDS: allow 5432 ONLY from the app tasks (remove any 0.0.0.0/0 rules on RDS)
aws ec2 authorize-security-group-ingress --group-id $RDS_SG --protocol tcp --port 5432 --source-group $APP_SG
```

Then in the RDS console: **Modify → Publicly accessible = No**. The DB stops
accepting anything from the public internet, including your laptop.

---

## 3. Store secrets (never bake them into the image)

```powershell
# Generate a strong Flask session key once
$SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"

aws secretsmanager create-secret --name cpi/secret_key  --secret-string $SECRET_KEY
aws secretsmanager create-secret --name cpi/pg_password --secret-string "Y8eCCFN4BRPdQrHlbML0"
# Optional: bootstrap admin password used once at first boot
aws secretsmanager create-secret --name cpi/bootstrap_admin_password --secret-string "ChangeMe!123"
```

Copy the full ARNs into `task-definition.json` under `secrets[*].valueFrom`.

---

## 4. IAM roles

### 4a. Task **execution** role (pulls image, reads secrets, writes logs)

```powershell
aws iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document `
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name ecsTaskExecutionRole `
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Grant secret reads (inline policy)
$SECRETS_POLICY = @'
{ "Version":"2012-10-17","Statement":[
  { "Effect":"Allow","Action":["secretsmanager:GetSecretValue"],
    "Resource":"arn:aws:secretsmanager:*:*:secret:cpi/*" }
]}
'@
$SECRETS_POLICY | Out-File -Encoding ascii secrets.json
aws iam put-role-policy --role-name ecsTaskExecutionRole `
  --policy-name cpi-secrets-read --policy-document file://secrets.json
```

### 4b. Task role (your app's own AWS permissions — empty for now)

```powershell
aws iam create-role --role-name cpiInventoryTaskRole --assume-role-policy-document `
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

---

## 5. Build and push the image to ECR

```powershell
aws ecr create-repository --repository-name $REPO --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region $REGION | `
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# IMPORTANT: build linux/amd64 on Windows/ARM
docker build --platform=linux/amd64 -t "$REPO:latest" .
docker tag  "$REPO:latest" "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
docker push "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
```

---

## 6. Register the task definition

1. Open `deploy/ecs/task-definition.json`.
2. Replace all `<ACCOUNT_ID>`, `<REGION>`, `<RDS_ENDPOINT>`, and secret ARNs.
3. Register:

```powershell
aws ecs register-task-definition --cli-input-json file://deploy/ecs/task-definition.json
```

---

## 7. Create the cluster, ALB, target group, listener, service

```powershell
aws ecs create-cluster --cluster-name $CLUSTER

# --- ALB (public) ---
$SUBNETS_PUBLIC  = "subnet-aaa,subnet-bbb"       # >=2 public subnets
$SUBNETS_PRIVATE = "subnet-ccc,subnet-ddd"       # >=2 private subnets (with NAT)

$ALB_ARN = (aws elbv2 create-load-balancer --name cpi-alb `
  --subnets $SUBNETS_PUBLIC.Split(',') `
  --security-groups $ALB_SG --scheme internet-facing --type application `
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

# --- Target group (ip-target for Fargate) ---
$TG_ARN = (aws elbv2 create-target-group --name cpi-tg `
  --protocol HTTP --port 8050 --vpc-id $VPC_ID --target-type ip `
  --health-check-path /api/v1/health --health-check-interval-seconds 30 `
  --healthy-threshold-count 2 --unhealthy-threshold-count 3 `
  --matcher "HttpCode=200" `
  --query 'TargetGroups[0].TargetGroupArn' --output text)

# --- Listener :80 (add :443 with an ACM cert once DNS is set) ---
aws elbv2 create-listener --load-balancer-arn $ALB_ARN --protocol HTTP --port 80 `
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# --- Service ---
aws ecs create-service `
  --cluster $CLUSTER --service-name $SERVICE --task-definition $FAMILY `
  --desired-count 2 --launch-type FARGATE `
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_PRIVATE.Split(',')],securityGroups=[$APP_SG],assignPublicIp=DISABLED}" `
  --load-balancers "targetGroupArn=$TG_ARN,containerName=app,containerPort=8050" `
  --health-check-grace-period-seconds 60 `
  --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}"
```

> Run the tasks in **private subnets** with NAT for outbound internet (ECR,
> Secrets Manager). If you don't have NAT, use private subnets + VPC endpoints
> for `ecr.api`, `ecr.dkr`, `logs`, `secretsmanager`, `s3` (gateway).

Grab the ALB DNS name:

```powershell
aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN `
  --query 'LoadBalancers[0].DNSName' --output text
```

Open `http://<alb-dns>/` — you should see the login page. Then add HTTPS:

1. Request an ACM certificate for your domain in the **same region**.
2. Point DNS (Route53 or your provider) to the ALB.
3. `aws elbv2 create-listener ... --protocol HTTPS --port 443 --certificates CertificateArn=... --default-actions Type=forward,TargetGroupArn=$TG_ARN`
4. Optional: redirect :80 → :443.

---

## 8. First-time DB bootstrap (one-off tasks)

These use the same task definition but override the container command. The app
connects to RDS from inside the VPC (same subnets/SG as the service), so no
public DB access is required.

### 8a. Wipe all tables (prod starts empty)

```powershell
aws ecs run-task --cluster $CLUSTER --launch-type FARGATE `
  --task-definition $FAMILY `
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_PRIVATE.Split(',')],securityGroups=[$APP_SG],assignPublicIp=DISABLED}" `
  --overrides '{"containerOverrides":[{"name":"app","command":["python","-m","database.clear_all_data","--yes"]}]}'
```

### 8b. Create the first admin user

The container reads `CPI_BOOTSTRAP_ADMIN_*` env/secret. Add these to the task
definition *only* for this run by extending the override, or permanently under
`environment`/`secrets`:

```powershell
aws ecs run-task --cluster $CLUSTER --launch-type FARGATE `
  --task-definition $FAMILY `
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_PRIVATE.Split(',')],securityGroups=[$APP_SG],assignPublicIp=DISABLED}" `
  --overrides '{
    "containerOverrides":[{
      "name":"app",
      "command":["python","-m","database.create_bootstrap_admin"],
      "environment":[
        {"name":"CPI_BOOTSTRAP_ADMIN_USERNAME","value":"admin"},
        {"name":"CPI_BOOTSTRAP_ADMIN_EMAIL","value":"admin@example.com"}
      ],
      "secrets":[
        {"name":"CPI_BOOTSTRAP_ADMIN_PASSWORD","valueFrom":"arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:cpi/bootstrap_admin_password-XXXXXX"}
      ]
    }]
  }'
```

Tail the logs for either run in CloudWatch Logs group `/ecs/cpi-inventory`.

---

## 9. Rolling updates

```powershell
# Build & push a new image tag
$TAG = (Get-Date -Format "yyyyMMdd-HHmm")
docker build --platform=linux/amd64 -t "$REPO:$TAG" .
docker tag  "$REPO:$TAG" "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:$TAG"
docker push "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:$TAG"

# Edit task-definition.json -> image tag -> $TAG, then:
aws ecs register-task-definition --cli-input-json file://deploy/ecs/task-definition.json
aws ecs update-service --cluster $CLUSTER --service $SERVICE `
  --task-definition $FAMILY --force-new-deployment
```

The deployment circuit breaker auto-rolls back if the new tasks fail their
ALB health checks.

---

## 10. Tuning checklist for prod

- **RDS**: Publicly accessible = No; SG allows 5432 only from app SG.
- **App env**: `CPI_ENV=production`, `CPI_SEED_MODE=minimal`,
  `CPI_BEHIND_PROXY=1`, `CPI_SESSION_COOKIE_SECURE=1`.
- **Scaling**: start with desired=2 (HA across 2 AZs); attach
  Application Auto Scaling on CPU > 60 %.
- **Observability**: CloudWatch Logs + Container Insights + ALB access logs.
- **Backups**: RDS automated backups + at least one manual snapshot before
  first launch.
- **Secrets**: only in Secrets Manager; rotate `cpi/secret_key` quarterly
  (triggers logout for all users).

---

## 11. Admin access to RDS from your laptop (optional)

You do NOT need to allow your laptop in the RDS SG. Instead:

```powershell
# Launch a tiny EC2 in a private subnet with SSM enabled, then:
aws ssm start-session --target i-xxxxxxxx `
  --document-name AWS-StartPortForwardingSessionToRemoteHost `
  --parameters '{"host":["<RDS_ENDPOINT>"],"portNumber":["5432"],"localPortNumber":["15432"]}'

# Now psql on localhost:15432 works from your PC:
psql "host=127.0.0.1 port=15432 dbname=ss_ims user=postgres sslmode=require"
```

No public DB, no SG rule for your IP, and it works from anywhere you have AWS
credentials.

# Running on AWS (ECS on Fargate)

These steps have **not** been run against a live AWS account. The Docker image itself is built and health-checked in CI.

1. Push the image to ECR:
   ```bash
   aws ecr create-repository --repository-name sequelagent
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker build --platform linux/amd64 -t <account>.dkr.ecr.<region>.amazonaws.com/sequelagent:latest .
   docker push <account>.dkr.ecr.<region>.amazonaws.com/sequelagent:latest
   ```
2. Store the model key in Secrets Manager (never in the image or the task definition).
3. Create a Fargate service (0.5 vCPU, 1 GB) with container port `8501`, health check path `/_stcore/health`, and the secret
   exposed as `OPENAI_API_KEY`.
4. Put it behind a load balancer **with authentication** (for example Cognito on the ALB). The app has no login and only a per-session
   rate limit, so a public URL would let anyone spend your model budget.

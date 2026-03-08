# Secret template (DO NOT commit real values)
# Apply with kubectl:
#   kubectl create secret generic platform-api-config \
#     --namespace openclaw-platform \
#     --from-literal=DATABASE_URL="postgresql+asyncpg://openclaw_admin:<PASSWORD>@<RDS_ENDPOINT>:5432/openclawsaas" \
#     --from-literal=JWT_SECRET="<RANDOM_64_HEX>" \
#     --from-literal=JWT_ALGORITHM="HS256" \
#     --from-literal=JWT_EXPIRE_HOURS="24" \
#     --from-literal=K8S_IN_CLUSTER="true" \
#     --from-literal=LOG_LEVEL="INFO"

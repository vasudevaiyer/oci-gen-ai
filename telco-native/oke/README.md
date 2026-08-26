# OKE deployment package

This deploys only the `telco-native` application. It does not deploy the
original VM app, Oracle Database Free, ORDS, or Ollama.

The OCI Vault wallet secret is not automatically available to Kubernetes.
Configure the cluster's approved OCI Vault/Secrets Store CSI integration, or
an approved synchronization process, to materialize a Kubernetes Secret named
`telco-adb-wallet` containing the wallet files. Mount it at `/opt/oracle/wallet`.

Create `telco-native-runtime` through the secret-management process. It must
contain `APP_SCHEMA_PASSWORD` and `ORACLE_WALLET_PASSWORD`; the current clone
also needs `OCI_GENAI_API_KEY` until its GenAI adapter is changed to OCI SDK
authentication with OKE Workload Identity.

Before applying, replace all `REPLACE_` values in `kustomization.yaml` and
`configmap.yaml`. Do not commit populated Secret files.

```bash
kubectl apply -f namespace.yaml
kubectl apply -k .
kubectl -n telco-native rollout status deployment/telco-native
kubectl -n telco-native get service telco-native
kubectl -n telco-native logs deployment/telco-native
```

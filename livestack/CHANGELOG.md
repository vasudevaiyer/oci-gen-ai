# Change Log

## 2026-08-27

- Added the VM-focused, application-owned Node/oracledb bootstrap service to `telco-native`, with versioned `LIVESTACK_NATIVE_MIGRATIONS` markers and an explicit `POST /api/bootstrap` endpoint.
- Added the standalone `scripts/bootstrap-native.js` runner and included database/scripts assets in the runtime image.
- Updated the VM Resource Manager cloud-init template to build the image and run the Node bootstrap inside the container; removed its SQL*Plus schema/data dependency. OKE artifacts were intentionally left unchanged.
- Verified JavaScript syntax and parsed all configured schema/data migration files without executing migrations against the already-seeded native VM.
- Extended the VM stack for clean rebuilds: Terraform now generates the ADB wallet into private Object Storage, grants the VM instance principal object-read access, and cloud-init downloads the wallet automatically.
- Added application-schema creation, vector table/index bootstrap without ONNX loading, and section-aware security migration execution for fresh ADBs. OKE remains out of scope.
- Destroyed the prior VM test stack successfully after retrying an OCI `NetworkSecurityGroup ... cannot be deleted since it still has vnics attached` error caused by the terminated ADB private endpoint. The original `RAGDEVORD` database was preserved; the next step is clean VM stack provisioning.

## 2026-08-13 (OKE access)

- Confirmed the OKE cluster is `ACTIVE` with two `Ready` nodes; the existing local kubeconfig selected an unreachable private endpoint.
- Added a temporary public-subnet bastion VM `telco-native-oke-bastion` at `163.192.219.218` and restricted SSH ingress to the workstation's current `/32` address. The bastion reaches the private Kubernetes API at `10.50.10.105:6443`.
- Established a temporary SSH tunnel through the bastion and verified `kubectl get nodes` and `kubectl get pods -A` successfully. No application workloads were applied yet.
- Deployment remains gated on a private OCIR image-pull credential and the missing Vault CSI/bootstrap resources; applying the current placeholder manifests would not produce a healthy application.
- Used the supplied OCIR auth token to create a temporary Kubernetes pull secret; private image pulls succeeded. Published an `oke-fixed-20260813` image using node-oracledb Thin mode because the original image lacked Oracle Instant Client.
## 2026-08-26

- Completed native ADB repair on the public VM: created missing JSON/graph/vector/spatial tables and geometry metadata, loaded 3,000 service orders and 20 demand regions, and verified fulfillment, orders, and health APIs.
- Diagnosed the new public VM database failure: the Telco image was present, but the ADB wallet and runtime schema wiring were missing; the old bootstrap was a Python RAG bootstrap and attempted to clone a Git commit as a branch.
- Generated the new ADB wallet out-of-band, staged it only on the native VM, ensured `LIVESTACK_NATIVE` grants, and verified `http://147.224.133.80:8510/api/health` returns a healthy database connection.
- Replaced the Terraform bootstrap template with a Node/Podman Telco bootstrap using detached Git checkout, wallet validation, npm build, and a systemd-managed container. Terraform validation remains blocked by the local provider handshake issue; no credentials or wallet files were committed.

- Corrected the wallet service alias from `genaivasuatp_medium` to `ragdevord_public_medium`. Bootstrap then reached the existing ADB but failed with `ORA-12529`/`NJS-511`; the existing ADB allowlist did not admit the OKE connection despite a temporary NAT-IP allowlist test. The NAT entry was removed afterward and the original allowlist restored.
- Removed failed debug/bootstrap pods and temporary local wallet/password files. The OKE namespace, runtime secrets, pull secret, ConfigMap, application Deployment, and LoadBalancer Service remain for the next network-connectivity attempt.
- Corrected the target design to provision a new Autonomous AI Database 26ai instead of reusing `RAGDEVORD`: the reuse variable now defaults empty, the new ADB remains at 500 GB, and its private endpoint is placed in the OKE private subnet. The application schema password remains OCI Vault auto-generated.
- Terraform formatting passes, but local OCI provider schema initialization still fails before plan/apply (`terraform-provider-oci` plugin handshake), so the new ADB has not yet been created.
- Updated the OCI provider pin to 8.26.0; initialization and planning now work. The targeted new-ADB apply was rejected by OCI `QuotaExceeded` for `atp-total-storage-tb` because the existing ADB consumes the available Autonomous Database storage quota. No new ADB was created. Restored the OKE private load-balancer security rules and imported the existing temporary bastion into Terraform state.
- Pause checkpoint: the requested target remains a new private 26ai ADB with 500 GB in the OKE VCN. OCI reports `atp-total-storage-tb` availability `0`; request quota for the existing database plus the new 500 GB database before retrying. The existing `RAGDEVORD` ADB was not modified.

## 2026-08-13

- Corrected OKE node image selection to use the OL8 x86_64 1.36.1 image with `VM.Standard.E5.Flex`.
- Added the required OKE API endpoint security rules for worker-node TCP/6443, NAT egress TCP/6443, and TCP/12250; the recreated `telco-native-nodes` pool is `ACTIVE` with two registered `ACTIVE` nodes.
- Added encrypted Object Storage wallet delivery, generated schema secret, DevOps build/deliver stages, and enabled DevOps service logging with a dedicated log group.
- The DevOps build run now reaches the pipeline but fails while fetching `build_spec.yaml` because the build pipeline dynamic group/policy is missing.
- Attempted to add a dedicated DevOps build dynamic group and compartment-scoped policies; OCI rejected it because the tenancy has reached its Dynamic Resource Groups object limit. Next action is to reuse an existing authorized DevOps dynamic group or request quota/cleanup.
- After one obsolete dynamic group was removed, the dedicated `telco-native-build-pipeline` dynamic group and policy were created successfully. A delayed retry confirmed source authorization: repository download and `build_spec.yaml` parsing succeeded, and the container image build completed. The subsequent OCIR delivery stage failed with OCI's generic `Internal error, could not run the build`; the Terraform apply therefore did not retain the build-run resource. IAM/source access is resolved; OCIR delivery is the next bounded troubleshooting item.
- Read-only inspection of the hosted `build_spec.yaml` identified the delivery mismatch: the build exports the Docker image as `telco-native:${OCI_BUILD_RUN_ID}`, while the Terraform artifact version incorrectly used the build-stage OCID. Changed the artifact version to `OCI_BUILD_RUN_ID` for the next retry.
- The corrected artifact-version retry built successfully but OCIR delivery still failed. Comparing the hosted build specification with the Deliver stage found a second mismatch: output artifact `telco-native-image` versus configured deliver artifact name `telco-native-container-image`. Changed the Deliver stage to use the exact build-spec artifact name.
- The first attempt to update the Deliver stage was rejected by the OCI API as `Invalid description`; added a non-empty stage description required by the pinned OCI provider/API combination.
- Final DevOps retry succeeded: both the managed build and OCIR delivery stages completed successfully, and the `telco-native` OCIR repository reports one image. The Resource Manager checkpoint is complete through image publication. Remaining work is the Kubernetes-side OKE deployment: kubeconfig, Vault CSI, bootstrap Job, application/LoadBalancer manifests, and health validation.

## 2026-08-12

- Added a non-secret Resource Manager Terraform foundation under `resource-manager/` targeting the confirmed `cmp-lift-aigent-factory` compartment by default.
- Read the tenancy OCID from the local OCI CLI configuration and configured the local ignored `terraform.tfvars` accordingly; no private key or password was copied.
- Set OCI GenAI to `openai.gpt-oss-120b`, OKE to minor version `1.36`, and configured automatic selection of the latest OL8 x86_64 OKE image.
- Created the OCI Notifications topic `telco-native-build-events` in the confirmed compartment as a prerequisite for an OCI DevOps build project. Code Repository/project verification and repository creation were blocked by the current identity's `NotAuthorizedOrNotFound` response from the DevOps repository API; no application image was built or pushed.
- Created the OCI DevOps project `telco-native-build` and private hosted Code Repository `telco-native-source` in the confirmed compartment. The repository is empty pending a controlled source upload; no auth token was created and no source, image, or runtime secret was copied.
- Using the workstation's existing OCI signing key over DevOps SSH, pushed the sanitized native source to `telco-native-source` on `main` at commit `e525a76c056a91e585b8d8e3a6aac4cd4673776f`. Excluded wallets, `.env`, dependencies, legacy bootstrap credentials, and PAR URLs.
- Added `build_spec.yaml` to the hosted source and pushed commit `baf2102a6ecde433eab0af3949d84fed6326875a`; it validates the source and builds the application container during an OCI DevOps Managed Build.
- Extended `resource-manager/` with the private OCIR repository, DevOps build pipeline, build/deliver stages, Apply-triggered build run, and OCIR/build outputs. Terraform validation passes; no Resource Manager Apply was run.
- Added an idempotent `scripts/bootstrap-native.js`, `scripts/check-bootstrap.js`, OKE `bootstrap-job.yaml`, and Deployment init gate. The bootstrap image now contains the database schema/data assets and records `LIVESTACK_NATIVE_MIGRATIONS` after completion. Pushed source commit `a4cce69646301e66e02a11e898c70ac2e5467050`.
- Node syntax checks, Kustomize rendering, and Terraform validation passed. The bootstrap has not been run against a new database; vector model loading and DBMS_CLOUD_AI profile activation still require the dedicated database bootstrap phase.
- Added Terraform resources for an OCI KMS Vault, HSM-protected AES key, Autonomous Database wallet generation, and Vault secrets for the wallet and `LIVESTACK_NATIVE` schema password. Terraform validation passes; these resources have not been applied.
- Changed the `LIVESTACK_NATIVE` password secret to OCI Vault auto-generation; the stack no longer accepts or stores an application schema password input. Runtime bootstrap/CSI wiring must retrieve this generated value.
- The foundation defines a dedicated VCN with public load-balancer and private OKE subnets, Internet/NAT/Service Gateways, security lists, Enhanced OKE, a managed node pool, and Autonomous AI Database 26ai.
- Added stack outputs for the target compartment, VCN, OKE cluster, database, inference endpoint, and eventual application URL.
- No OCI resources were provisioned. `terraform validate` passed with OCI provider 8.26.0.
- Database schema/data bootstrap, Vault-backed secrets, vector population, Select AI activation, OCIR publication, and the OKE deployment Job remain the next bounded implementation phase.
- Added OCI Vault Secrets Store CSI/OKE Workload Identity wiring for the native workload: Vault-generated schema password, wallet password, wallet archive, `SecretProviderClass`, synced runtime secret, and wallet staging init step.
- Added a Resource Manager IAM policy scoped to the `telco-native` Kubernetes service account and Enhanced OKE cluster, plus file-based runtime-secret support to the bootstrap/check scripts.
- Terraform formatting completed. Kubernetes rendering and Node syntax checks pass; Terraform validation is currently blocked by the locally installed OCI provider 8.26.0 failing its plugin schema handshake.
- Pushed the Vault/CSI OKE wiring to the hosted DevOps source repository as commit `c636695` on `main`.
- Changed new serverless ECPU ADB sizing to `data_storage_size_in_gb = 500`; the stack continues reusing the existing Vault and key in `cmp-lift-aigent-factory`.
- Replaced the oversized Vault wallet secret with a private KMS-encrypted Object Storage bucket/object. OKE downloads and decodes the wallet with Workload Identity during pod initialization. Pushed source commit `886e7cf`; Terraform validation and the 9-resource plan pass.
- End-of-day checkpoint: stop here and resume tomorrow with the DevOps build-stage image correction, Terraform state refresh, 9-resource Object Storage plan apply, OKE node pool/CSI provider setup, manifest substitution, application deployment, and LoadBalancer health verification. No application pods or LoadBalancer URL have been deployed yet.
- Began OCI deployment. VCN/networking, primary Enhanced OKE cluster `telco-native-oke` (`v1.36.1`), OCIR repository, DevOps build pipeline, wallet generation, and wallet-password secret were created; an unintended duplicate OKE cluster was removed. Application/LB deployment remains blocked by tenancy/API constraints: ADB wallet exceeds Vault's 25,600-byte secret limit, IAM policy writes require home region FRA, node image/shape compatibility needs adjustment, Vault auto-generation needs a generation context, and DevOps build stage image must use a tenancy-supported image identifier.

## 2026-08-11

- Installed OKE administration tooling on the target VM: checksum-verified `kubectl` v1.36.3, Helm v4.1.1, OCI CLI 3.83.0, and bundled Kustomize v5.8.1. The VM has no kubeconfig, and its OCI instance principal is not currently authorized to list OKE clusters.
- Added a non-secret OKE deployment package under the native clone's `oke/` directory on the target VM. It includes Kustomize configuration, namespace, service account, ConfigMap, Deployment, LoadBalancer Service, health probes, resource limits, and a runtime Secret template.
- The OKE package expects `telco-adb-wallet` and `telco-native-runtime` Kubernetes Secrets to be populated through the approved OCI Vault synchronization path; no wallet, password, API key, OCID, or PAR URL was copied into the package.
- OKE access and OCI CLI tooling were not configured on the target VM, so cluster deployment remains pending cluster kubeconfig, OCIR image details, and secret synchronization setup.

## 2026-07-30

- Read-only inspection confirmed the original app uses Oracle Database Free features for both the `telecom_experience_network` SQL/PGQ property graph and `SDO_GEOMETRY` spatial field-operations flows.
- Confirmed graph results are returned through Express APIs and rendered client-side with D3 force layout in SVG; spatial layers are returned as JSON/GeoJSON and rendered in the browser.
- Identified the current integration gap: graph subscriber, network-site, and field-crew entities do not have formal foreign-key bridges to customer, fulfillment-center, or crew-location records.
- Recorded the recommended native migration pattern: graph traversal followed by relational spatial functions through explicit bridge tables, while leaving geometry in normalized spatial tables.
- Confirmed the migration boundary: do not modify the original app; build an isolated `telco-native` clone with a separate container, Compose project, port (planned `8510`), images, environment, and volumes while preserving the original port `8505` deployment.
- Created the isolated `LIVESTACK_NATIVE` schema in the wallet-backed `genaivasuatp` Autonomous Database and loaded the cloned relational, JSON, graph, spatial, telecom, and forecast seed data. Verified 2,000 customers, 3,000 orders, 5,000 signal posts, 36 telecom graph entities, 50 graph relationships, 2,000 customer geometries, and 48 fulfillment zones.
- Deferred the ONNX embedding model and DBMS_CLOUD_AI/DBMS_CLOUD_AI_AGENT activation because the first native clone milestone will use application-side OCI Generative AI inference; vector structures are present but not populated yet.
- Created `/u01/scripts/livestack/telco-native` as an isolated one-container clone on port `8510`, with its own Compose project, image, runtime environment, and read-only ADB wallet mount. The original app remains healthy on port `8505`.
- Replaced the clone’s Ollama transport with an OCI OpenAI-compatible Chat Completions adapter, preserving existing SQL generation, repair, validation, execution, and summarization interfaces. End-to-end `/api/selectai/runsql` succeeded against `LIVESTACK_NATIVE` using the hosted OCI model.
- Increased OCI generation budgets for the reasoning model after an initial response exhausted its token budget before emitting final JSON.
- Documented the OCI GenAI trigger map: Select AI and agent APIs invoke the hosted model; graph, spatial, ordinary data-loading APIs, profile listing, and deterministic SQL paths do not.

## 2026-07-27

- Confirmed the deployed Telco source is on the target VM at `/u01/scripts/livestack/telco`.
- Verified the original app uses Ollama `llama3.2` for application-side SQL generation, repair, and selected summarization.
- Verified SQL execution is performed directly by Oracle through `node-oracledb`.
- Verified ORDS is a separate HTTP/SQL Developer Web gateway and is not the normal application SQL path.
- Documented the native OCI migration approach: OCI AI Database, database-side `DBMS_CLOUD_AI`, native Select AI, vector/RAG, and database agents.
- Added `AGENTS.md`, `CONTEXT.md`, and this changelog to reduce repeated discovery across sessions.

### Next session

- Verify the chosen OCI AI Database target and network/authentication prerequisites.

# Current Context

Last verified: 2026-08-27

## 2026-08-27 VM handoff checkpoint

The current objective is to hand a team a reproducible VM-based native Telco
stack for test-environment spin-up. OKE is out of scope.

- The sanitized VM Resource Manager package is `resource-manager-telco/`.
- Commit `48c67c2` is pushed to `origin/main`; it includes the complete stack package and clean-rebuild fixes.
- Terraform now creates the ADB wallet and stores it in a private Object Storage bucket/object. VM cloud-init downloads it with instance-principal authentication.
- Cloud-init supports the repository-root source URL and automatically selects the `telco-native/` application subdirectory.
- The Node bootstrap creates the application schema, records versioned migrations in `LIVESTACK_NATIVE_MIGRATIONS`, creates vector tables/indexes while leaving ONNX loading deferred, and runs the sectioned security migration.
- The prior native test VM and `NATIVEDEVORD` ADB are now terminated after a successful Resource Manager destroy. The original `RAGDEVORD` ADB remains available; OKE resources remain running and are out of scope.
- The destroy initially encountered a stale ADB private-endpoint VNIC attached to `telco-native-dev-ord-adb-nsg`; a retry succeeded after OCI cleanup.
- Next action: provision the VM Resource Manager test stack from `origin/main`, then validate wallet delivery, schema creation, migrations, health, seeded data, and restart behavior.
- Do not modify the original VM at `163.192.117.244` or begin OKE deployment work.

## Deployment

| Item | Verified value |
|---|---|
| Target VM | `163.192.117.244` (`opc`) |
| Original source | `/u01/scripts/livestack/telco` |
| Original app | `http://163.192.117.244:8505` |
| Original stack | app, Oracle Free DB, ORDS, Ollama |
| Original LLM | Ollama `llama3.2` at `http://ollama:11434` |
| Original SQL execution | `node-oracledb` directly to Oracle |
| ORDS role | HTTP/SQL Developer Web gateway; not normal app SQL path |

## Target design

Build a separate `/u01/scripts/livestack/telco-native` application using OCI AI Database 26ai and database-native OCI AI:

- `DBMS_CLOUD_AI` / native `SELECT AI`
- Oracle AI Vector Search and database-side RAG
- `DBMS_CLOUD_AI_AGENT` where applicable
- No dependency on the original Ollama service

## Current phase

OCI infrastructure provisioning is complete through image publication. The
VCN, primary Enhanced OKE cluster `telco-native-oke` (`v1.36.1`), and healthy
two-node pool `telco-native-nodes` are active. The existing 26ai ADB and
existing Vault/key in `cmp-lift-aigent-factory` are being reused. The Terraform
stack uses 500 GB serverless ECPU ADB storage and an encrypted Object Storage
wallet instead of a Vault wallet secret. The DevOps pipeline successfully
published one image to the `telco-native` OCIR repository.

The active primary cluster OCID is recorded in the Terraform state. The
unintended duplicate cluster was deleted. Do not start a second OKE apply
without refreshing state first.

## Next actions when work resumes

### 2026-08-26 resume checkpoint

The public VM deployment is reachable at `147.224.133.80:8510` and the
application's Node `oracledb` connection to the new ADB is healthy. The initial
cloud-init path omitted database DDL and seed execution. SQL*Plus/Instant
Client was installed temporarily and used with an explicit `TNS_ADMIN` wallet
configuration to repair the schema and seed the core Telco data. The current
database has fulfillment centers, orders, demand regions, customers, signal
posts, graph data, users, and forecasts; ONNX/vector population is deferred.

The RAG pipeline stack shows the preferred durable design: the application
owns an idempotent `node-oracledb` schema initializer invoked by
`POST /api/bootstrap`. The Telco clone should implement the same pattern,
including migration versioning and expected-error handling, rather than making
host SQL*Plus a runtime dependency. Wallet generation/delivery must also be
automated in Terraform (private Object Storage plus instance-principal read)
before a destroy/recreate test.

1. Use the verified bastion tunnel for OKE administration; import or remove the temporary bastion after deployment.
2. Install/configure the OCI Vault Secrets Store CSI provider and substitute
   Terraform outputs (bucket, Vault secret names, and published OCIR image)
   into the OKE manifests.
3. Deploy the database bootstrap Job, then deploy the native application and
   LoadBalancer service.
4. Wait for the LoadBalancer external IP and verify `/api/health`, database
   connectivity, ontology queries, and seeded schema data.
5. Continue vector/semantic population and OCI GenAI validation.

Source repository latest commit: `886e7cf` on `main`.

Known remaining issues: the OKE CSI provider and application manifests have
not yet been applied; the LoadBalancer endpoint is not yet provisioned; and
the current GenAI adapter still expects `OCI_GENAI_API_KEY`.

Deployment update (2026-08-13): OKE access, private OCIR pulls, wallet
mounting, and Thin-mode Oracle driver startup are working. The bootstrap is
blocked at the existing `RAGDEVORD` ADB network boundary with `ORA-12529`
from the public service alias. The OKE NAT IP was tested in the ADB allowlist
and then removed; the original ADB allowlist was restored. The next action is
to establish supported private connectivity or determine the actual egress
source admitted by the ADB before retrying bootstrap.

Target correction (2026-08-13): the migration target is now a new Autonomous
AI Database 26ai provisioned in the native OKE VCN/private subnet with 500 GB
serverless storage. `adb_admin_password` is supplied as a sensitive runtime
variable, while the `LIVESTACK_NATIVE` application password remains Vault
auto-generated. The existing `RAGDEVORD` database is not the intended target.
The Terraform code is corrected, but creation is pending recovery from the
local OCI provider plugin handshake failure. Provider 8.26.0 now initializes
and the new-ADB plan is valid, but OCI rejected creation with
`QuotaExceeded: atp-total-storage-tb`; the existing ADB consumes the current
Autonomous Database storage quota. No new ADB was created. Request a quota
increase before retrying the targeted ADB apply. The temporary bastion is now
imported into Terraform state.

Pause checkpoint (2026-08-13): the requested 500 GB new ADB was not created.
OCI reports `atp-total-storage-tb` availability `0` because the existing ADB
consumes the available allocation. Request quota sufficient for the existing
database plus a new 500 GB database before resuming. Do not delete or modify
the existing `RAGDEVORD` ADB. Resume with the targeted new-ADB apply, then
refresh state, generate the new wallet, update the encrypted Object Storage
wallet object, bootstrap `LIVESTACK_NATIVE`, and retry the OKE deployment.

OKE access update (2026-08-13): a temporary public-subnet bastion
`telco-native-oke-bastion` was created at `163.192.219.218` because the local
environment could not reach the private OKE endpoint. SSH is restricted to the
current workstation `/32`; a temporary tunnel through the bastion successfully
verified both OKE nodes and the system pods. The bastion is not yet imported
into Terraform state and should be removed after deployment access is no longer
needed.

## Important distinction

The current web `/api/selectai` implementation uses `backend/lib/ollamaAssistant.js`; it is application-side SQL generation. Native Oracle `SELECT AI` profiles in `db/schema/07_ai_profile.sql` are a separate database-side path and already specify OCI providers.

The native clone uses `backend/lib/ociGenaiAssistant.js` with OCI's OpenAI-compatible `/chat/completions` endpoint. The existing SQL-generation, repair, validation, execution, and summarization contracts remain in place; only the model transport, message format, response extraction, and OCI-specific token budgets changed.

### OCI GenAI trigger map

The native app invokes OCI GenAI through these API paths:

- `/api/selectai/chat` and `/api/selectai/chat-mode`: model SQL generation when no deterministic SQL pattern matches, plus conversational summarization for larger result sets.
- `/api/selectai/showsql`: model-generated SQL.
- `/api/selectai/runsql`: model-generated SQL, with model repair after retryable Oracle SQL errors.
- `/api/agents/ask`, `/api/agents/trends`, `/api/agents/fulfillment`, and `/api/agents/commerce`: summarize database context for the selected team.
- `/api/agents/chat`: routes a question to a team and uses OCI GenAI reasoning, with direct SQL/PL/SQL fallback.
- `/api/agents/run-cycle`: best-effort OCI GenAI analysis during orchestration, with SQL fallback.

The Ask Data and Agent Console frontend pages call these routes. Graph APIs (`/api/graph/*`), spatial/field APIs (`/api/fulfillment/*`), ordinary dashboard/order/product queries, and `/api/selectai/profiles` do not invoke the model. Deterministic SQL questions also bypass OCI GenAI.

## Graph and spatial findings

The original deployment already demonstrates both subscriber/network graph analysis and spatial field operations, but both run in the local Oracle Database Free container on the VM. They are not using OCI Maps, OCI Generative AI, or another OCI-managed graph/spatial service.

### Property graph

- `db/schema/10_telecom_network_graph.sql` defines the `telecom_experience_network` property graph.
- Vertex and edge data is stored in relational tables: `telecom_graph_entities`, `telecom_graph_relationships`, `telecom_experience_cases`, and `telecom_case_entities`.
- Entity types include subscribers, service lines, network sites, outages, support cases, devices, and field crews.
- Relationships include `served_by`, `assigned_crew`, `impacted_by`, `service_path`, and `capacity_dependency`.
- Example queries use Oracle `GRAPH_TABLE` / SQL-PGQ. The normal ego-network API also performs bounded relational hop queries in `backend/routes/graph.js`.
- The graph entities are synthetic and do not currently have formal `customer_id`, `center_id`, or crew-location foreign keys.

### Spatial and field operations

- `db/schema/05_spatial.sql` stores WGS84 `SDO_GEOMETRY` points for customers and fulfillment centers.
- Fulfillment zones and demand regions store polygon geometries, with Oracle Spatial indexes where applicable.
- `/api/fulfillment/nearest` uses `SDO_GEOM.SDO_DISTANCE`; demand-region responses use `SDO_UTIL.TO_GEOJSON` for browser mapping.
- The frontend renders graph results in `frontend/src/pages/InfluencerGraph.jsx` with React, D3, and SVG. D3 calculates the force-directed layout; the browser draws clickable nodes and edges. Oracle does not render the graph.
- Spatial map layers are likewise rendered in the browser from API JSON/GeoJSON; no OCI visualization service is involved.

### Migration implication

To combine subscriber-impact traversal with field operations, add an explicit bridge from graph entities to operational records (for example, a mapping table from graph `network_site` entities to `fulfillment_centers`, and from subscriber entities to customer/account records). Then perform graph traversal first and apply `SDO_NN`, `SDO_DISTANCE`, or `SDO_WITHIN_DISTANCE` to the bridged operational locations. Keep geometry in normalized spatial tables rather than embedding it directly in graph vertices unless a database-specific test proves that is useful.

## Clone isolation decision

The original `/u01/scripts/livestack/telco` deployment is out of scope for modification. The native migration will create and run `/u01/scripts/livestack/telco-native` as a separate application container and Compose project, using an independent application port (planned: `8510`), image name, environment file, and volume names. The clone will connect to OCI AI Database and OCI Generative AI while the original app remains available on port `8505` for comparison and rollback.

The clone is now deployed at `/u01/scripts/livestack/telco-native` with one application container, a read-only wallet mount, and port `8510`; it has no local Oracle, ORDS, or Ollama service.

## OCI database staging status

The wallet-backed Autonomous Database identified on this VM is `genaivasuatp` in `us-chicago-1`, using the wallet directory `/home/opc/wallet`. An isolated schema named `LIVESTACK_NATIVE` has been created for the clone. The original `LIVESTACK` schema and local Oracle container were not modified.

Loaded and verified in `LIVESTACK_NATIVE`:

- Core relational, JSON, graph, spatial, vector-table, comment, telecom graph, and semantic-view DDL.
- 12 brands, 32 products, 12 network sites, 2,000 customers, 3,000 orders, 9,053 order items, 483 influencers, 5,000 signal posts, 3,515 post/service mentions, 1,500 shipments, and 360 forecasts.
- 36 telecom graph entities, 50 relationships, 4 experience cases, and 26 case/entity links.
- 12 site geometries, 2,000 customer geometries, and 48 fulfillment-zone polygons.
- Both property graphs: `INFLUENCER_NETWORK` and `TELECOM_EXPERIENCE_NETWORK`.

Deferred intentionally for the first clone milestone:

- The bundled `ALL_MINILM_L12_V2` ONNX model was not loaded because the database-side `DATA_PUMP_DIR` file is not present. Vector tables and indexes exist, but embeddings are still empty.
- `07_ai_profile.sql` and `08_agents.sql` were not activated. The first clone will preserve application logic and call OCI Generative AI through its inference endpoint; database-native Select AI profiles can be configured after the application connection and OCI IAM/resource-principal path are validated.

# Working Instructions

## Scope

This workspace documents and incrementally develops a separate OCI-native clone of the Telco Livestack application. The original application runs on a remote VM and must remain unchanged unless explicitly requested.

## Environment

- Target VM: `opc@163.192.117.244`
- SSH key: `./livestackvm.key`
- Original source: `/u01/scripts/livestack/telco`
- Native clone target: `/u01/scripts/livestack/telco-native`
- Original app URL: `http://163.192.117.244:8505`

Commands for the deployed app must run over SSH on the target VM. Perform read-only checks before any change.

## Change policy

- Do not modify the original deployment while building the native clone.
- Use separate Compose projects, ports, images, volumes, and environment files for the clone.
- Make small, reversible, documented changes.
- Never commit credentials, private keys, wallets, database passwords, API keys, or PAR URLs.
- Verify each change with the smallest relevant health check or test.
- Preserve unrelated user changes in the working tree.

## 2026-08-27 handoff checkpoint

- Current scope is the VM-based native clone and its sanitized Resource Manager package. OKE deployment is explicitly out of scope for this test/handoff.
- The reproducible stack is under `resource-manager-telco/`; its source checkout uses `main` from the pushed repository and resolves the `telco-native/` application subdirectory automatically.
- Commit `48c67c2` is pushed to `origin/main` and includes the complete sanitized VM stack plus the bootstrap fixes.
- Terraform now generates the ADB wallet, stores it in a private Object Storage object, grants the VM instance principal object-read access, and downloads the wallet during cloud-init.
- The application bootstrap creates the app schema with the ADB admin connection, records versioned migrations in `LIVESTACK_NATIVE_MIGRATIONS`, creates vector tables/indexes without loading the deferred ONNX model, and applies the sectioned security migration.
- The prior test VM and `NATIVEDEVORD` ADB were successfully destroyed after an OCI stale-ADB-VNIC retry. The original `RAGDEVORD` database remains available; OKE resources remain running and are out of scope.
- The next action is to provision the VM Resource Manager stack from `origin/main`, then validate wallet delivery, app-schema creation, migrations, health, seeded data, and restart behavior. Never modify the original VM at `163.192.117.244`.

## Session workflow

1. Read `CONTEXT.md` and the latest `CHANGELOG.md` entry.
2. Confirm the current migration phase and next action.
3. Inspect the target VM state read-only.
4. Make one bounded change.
5. Record the result in `CHANGELOG.md`.

Detailed reference documents:

- `telco-codebase-observations.md`
- `telco-native-oci-migration.md`
- `deployment-troubleshooting.md`

## 2026-08-26 checkpoint

- The fresh public native VM is `147.224.133.80`; the original VM remains `163.192.117.244` and must not be modified while working on the clone.
- The native app connects successfully to the new private ADB through wallet service alias `nativedevord_low` and serves port `8510`.
- The first VM bootstrap created only the schema user; it did not execute the Telco DDL/seed phase. Manual repair then installed Oracle Instant Client/SQL*Plus, configured an explicit wallet `TNS_ADMIN`, created missing schema objects, and loaded core data.
- Current manual ADB repair results: 12 fulfillment centers, 3,000 orders, 20 demand regions, 2,000 customers, 5,000 signal posts, graph data, users, and forecasts. ONNX embeddings remain intentionally deferred.
- The RAG stack's proven pattern is application-owned bootstrap through `node-oracledb` (`POST /api/bootstrap` calling an idempotent schema initializer), not host SQL*Plus. The Telco clone should adopt this pattern.
- Before destroying/recreating the stack, add a Telco bootstrap endpoint/runner, migration marker/versioning, and automated wallet delivery. Do not rely on manually staged wallet files or SQL*Plus as the final design.

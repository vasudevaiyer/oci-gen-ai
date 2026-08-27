const fs = require('fs');
const path = require('path');
const db = require('../config/database');
const { oracledb } = db;

const MIGRATION_TABLE = 'LIVESTACK_NATIVE_MIGRATIONS';
const MIGRATIONS = [
  ['001-schema-tables', 'db/schema/01_tables.sql'],
  ['002-schema-json', 'db/schema/02_json_collections.sql'],
  ['003-schema-graph', 'db/schema/03_graph.sql'],
  ['004-schema-vector', 'db/schema/04_vector_tables.sql'],
  ['005-schema-spatial', 'db/schema/05_spatial.sql'],
  ['006-schema-comments', 'db/schema/09_comments.sql'],
  ['007-schema-telecom', 'db/schema/10_telecom_network_graph.sql'],
  ['008-schema-views', 'db/schema/11_telecom_views.sql'],
  ['009-data-all', 'db/data/load_all_data.sql'],
  ['010-data-telecom-graph', 'db/data/load_telecom_network_graph.sql'],
  ['011-data-fulfillment-zones', 'db/data/seed_fulfillment_zones.sql'],
  ['012-schema-security', 'db/schema/06_security.sql'],
];

let bootstrapPromise = null;

function identifier(value, label) {
  if (!/^[A-Za-z][A-Za-z0-9_$#]{0,127}$/.test(value || '')) {
    throw new Error(`${label} must be a simple Oracle identifier`);
  }
  return `"${value.toUpperCase()}"`;
}

function adminConnectionConfig() {
  if (!process.env.BOOTSTRAP_ADMIN_PASSWORD) {
    throw new Error('BOOTSTRAP_ADMIN_PASSWORD is required to create the application schema');
  }
  return {
    user: process.env.BOOTSTRAP_ADMIN_USER || 'ADMIN',
    password: process.env.BOOTSTRAP_ADMIN_PASSWORD,
    connectString: process.env.ORACLE_CONNECTION_STRING,
    walletLocation: process.env.ORACLE_WALLET_LOCATION,
    walletPassword: process.env.ORACLE_WALLET_PASSWORD,
    configDir: process.env.ORACLE_WALLET_LOCATION,
  };
}

async function ensureApplicationSchema() {
  const schema = identifier(process.env.ORACLE_USER || 'LIVESTACK_NATIVE', 'ORACLE_USER');
  const password = String(process.env.APP_SCHEMA_PASSWORD || '');
  if (!password) throw new Error('APP_SCHEMA_PASSWORD is required to create the application schema');
  const admin = await oracledb.getConnection(adminConnectionConfig());
  try {
    const userName = schema.slice(1, -1);
    const passwordLiteral = `"${password.replace(/"/g, '""')}"`;
    await admin.execute(`
      DECLARE n NUMBER;
      BEGIN
        SELECT COUNT(*) INTO n FROM dba_users WHERE username = '${userName}';
        IF n = 0 THEN
          EXECUTE IMMEDIATE 'CREATE USER ${schema} IDENTIFIED BY ${passwordLiteral} DEFAULT TABLESPACE DATA TEMPORARY TABLESPACE TEMP QUOTA UNLIMITED ON DATA';
        END IF;
      END;
    `);
    for (const grant of [
      'CREATE SESSION', 'CREATE TABLE', 'CREATE VIEW', 'CREATE SEQUENCE',
      'CREATE PROCEDURE', 'CREATE PACKAGE', 'CREATE TRIGGER', 'CREATE TYPE',
      'CREATE JOB', 'UNLIMITED TABLESPACE',
    ]) await admin.execute(`GRANT ${grant} TO ${schema}`);
    for (const grant of ['SODA_APP', 'GRAPH_DEVELOPER', 'AUDIT_ADMIN']) {
      try { await admin.execute(`GRANT ${grant} TO ${schema}`); } catch (err) {
        if (!/ORA-01919|ORA-01031/.test(err.message || '')) throw err;
      }
    }
    for (const object of ['MDSYS.SDO_GEOM', 'MDSYS.SDO_UTIL', 'MDSYS.SDO_CS', 'SYS.DBMS_RLS']) {
      try { await admin.execute(`GRANT EXECUTE ON ${object} TO ${schema}`); } catch (err) {
        if (!/ORA-04042|ORA-01031/.test(err.message || '')) throw err;
      }
    }
    await admin.commit();
  } finally {
    await admin.close();
  }
}

function section(source, start, end) {
  const startAt = source.indexOf(start);
  if (startAt < 0) throw new Error(`Missing SQL section marker: ${start}`);
  const bodyStart = startAt + start.length;
  const endAt = end ? source.indexOf(end, bodyStart) : source.length;
  return source.slice(bodyStart, endAt < 0 ? source.length : endAt);
}

async function runSecurityMigration(connection) {
  const file = path.resolve(__dirname, '../..', 'db/schema/06_security.sql');
  const source = fs.readFileSync(file, 'utf8');
  const schema = identifier(process.env.ORACLE_USER || 'LIVESTACK_NATIVE', 'ORACLE_USER');
  const admin = await oracledb.getConnection(adminConnectionConfig());
  try {
    const adminSql = section(source, '-- SECTION 1: RUN AS ADMIN', '-- SECTION 2: RUN AS LIVESTACK')
      .replace(/\blivestack\b/gi, schema);
    for (const statement of parseSqlScript(adminSql)) await admin.execute(statement);
    await admin.commit();
  } finally {
    await admin.close();
  }
  const appSql = section(source, '-- SECTION 2: RUN AS LIVESTACK');
  for (const statement of parseSqlScript(appSql)) await connection.execute(statement);
  await connection.commit();
}

function parseSqlScript(source) {
  const statements = [];
  let buffer = [];
  let plsql = false;
  const flush = () => {
    const sql = buffer.join('\n').trim().replace(/;\s*$/, '');
    if (sql) statements.push(sql);
    buffer = [];
    plsql = false;
  };
  for (const line of source.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (/^(SET|PROMPT|SPOOL|WHENEVER)\b/i.test(trimmed)) continue;
    if (trimmed === '/') { if (plsql) flush(); continue; }
    buffer.push(line);
    if (buffer.length === 1) {
      plsql = /^(DECLARE|BEGIN|CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|PACKAGE|TRIGGER)\b)/i.test(trimmed);
    }
    if (!plsql && /;\s*$/.test(line)) flush();
  }
  flush();
  return statements;
}

async function ensureMigrationTable(connection) {
  try {
    await connection.execute(`CREATE TABLE ${MIGRATION_TABLE} (version VARCHAR2(100) PRIMARY KEY, applied_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL)`);
  } catch (err) {
    if (err.errorNum !== 955 && !/ORA-00955/.test(err.message || '')) throw err;
  }
}

async function initializeSchema() {
  if (bootstrapPromise) return bootstrapPromise;
  bootstrapPromise = (async () => {
    await ensureApplicationSchema();
    const connection = await db.getConnection();
    try {
      await ensureMigrationTable(connection);
      const result = await connection.execute(`SELECT version FROM ${MIGRATION_TABLE}`);
      const applied = new Set(result.rows.map((row) => row.VERSION || row.version));
      const completed = [];
      for (const [version, relativeFile] of MIGRATIONS) {
        if (applied.has(version)) continue;
        if (version === '012-schema-security') {
          await runSecurityMigration(connection);
          await connection.execute(`INSERT INTO ${MIGRATION_TABLE} (version) VALUES (:version)`, { version });
          await connection.commit();
          completed.push({ version, file: relativeFile, statements: 'sectioned' });
          continue;
        }
        const file = path.resolve(__dirname, '../..', relativeFile);
        if (!fs.existsSync(file)) throw new Error(`Migration file not found: ${relativeFile}`);
        const statements = parseSqlScript(fs.readFileSync(file, 'utf8'));
        for (const statement of statements) await connection.execute(statement);
        await connection.execute(`INSERT INTO ${MIGRATION_TABLE} (version) VALUES (:version)`, { version });
        await connection.commit();
        completed.push({ version, file: relativeFile, statements: statements.length });
      }
      return { status: 'complete', applied: completed };
    } finally {
      await connection.close();
    }
  })();
  try { return await bootstrapPromise; } finally { bootstrapPromise = null; }
}

async function status() {
  const result = await db.execute(`SELECT version, applied_at FROM ${MIGRATION_TABLE} ORDER BY version`);
  return result.rows;
}

module.exports = { initializeSchema, status, parseSqlScript, ensureApplicationSchema, MIGRATIONS };

const fs = require('fs');
const path = require('path');
const db = require('../config/database');

const MIGRATION_TABLE = 'LIVESTACK_NATIVE_MIGRATIONS';
const MIGRATIONS = [
  ['001-schema-tables', 'db/schema/01_tables.sql'],
  ['002-schema-json', 'db/schema/02_json_collections.sql'],
  ['003-schema-graph', 'db/schema/03_graph.sql'],
  ['004-schema-spatial', 'db/schema/05_spatial.sql'],
  ['005-schema-comments', 'db/schema/09_comments.sql'],
  ['006-schema-telecom', 'db/schema/10_telecom_network_graph.sql'],
  ['007-schema-views', 'db/schema/11_telecom_views.sql'],
  ['008-data-all', 'db/data/load_all_data.sql'],
  ['009-data-telecom-graph', 'db/data/load_telecom_network_graph.sql'],
  ['010-data-fulfillment-zones', 'db/data/seed_fulfillment_zones.sql'],
];

let bootstrapPromise = null;

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
    const connection = await db.getConnection();
    try {
      await ensureMigrationTable(connection);
      const result = await connection.execute(`SELECT version FROM ${MIGRATION_TABLE}`);
      const applied = new Set(result.rows.map((row) => row.VERSION || row.version));
      const completed = [];
      for (const [version, relativeFile] of MIGRATIONS) {
        if (applied.has(version)) continue;
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

module.exports = { initializeSchema, status, parseSqlScript, MIGRATIONS };

#!/usr/bin/env node

require('dotenv').config();
const db = require('../backend/config/database');
const bootstrap = require('../backend/lib/bootstrapService');

async function main() {
  await bootstrap.ensureApplicationSchema();
  await db.initialize();
  console.log(JSON.stringify(await bootstrap.initializeSchema(), null, 2));
}

main()
  .catch((err) => {
    console.error('Native database bootstrap failed:', err.stack || err);
    process.exitCode = 1;
  })
  .finally(async () => {
    await db.closePool();
  });

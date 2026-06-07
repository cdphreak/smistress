// Exports the FastAPI OpenAPI schema to openapi.json by invoking the backend.
// Requires the backend deps (uv). Run from frontend/: node scripts/dump-openapi.mjs
import { execSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const py = 'import json,sys; from app.main import app; sys.stdout.write(json.dumps(app.openapi()))';
const out = execSync(`uv --directory ../backend run python -c "${py}"`, { encoding: 'utf8' });
writeFileSync('openapi.json', out);
console.log('wrote openapi.json');

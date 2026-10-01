/**
 * Builds and starts ../docker-compose.yaml (app + Postgres) before the tests and deletes it,
 * volume included, afterwards. It runs under its own compose project name, so a stack you
 * started yourself with `docker compose up` is never touched.
 */
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const composeFile = fileURLToPath(new URL('../docker-compose.yaml', import.meta.url));

export default async function globalSetup(): Promise<(() => void) | void> {
  if (process.env.E2E_BASE_URL) return; // testing an existing deployment

  const project = `archboard-e2e-${randomBytes(4).toString('hex')}`;
  const port = process.env.E2E_PORT ?? '8097';
  const compose = (...args: string[]) =>
    execFileSync('docker', ['compose', '-f', composeFile, '-p', project, ...args], {
      env: { ...process.env, APP_PORT: port },
      stdio: 'inherit',
    });
  const down = () => compose('down', '-v', '--remove-orphans');

  try {
    // --wait returns once the app's healthcheck passes, i.e. it answers HTTP.
    compose('up', '-d', '--build', '--wait');
  } catch (err) {
    try {
      compose('logs', '--tail', '100');
    } finally {
      down();
    }
    throw err;
  }
  return down;
}

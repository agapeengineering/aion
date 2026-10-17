import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
const root = new URL('../apps/web/dist/', import.meta.url);
const html = await readFile(new URL('index.html', root), 'utf8');
await mkdir(new URL('es/', root), { recursive: true });
await writeFile(new URL('es/index.html', root), html.replace('<html lang="en">', '<html lang="es">').replace('Aion — A life, in weeks.', 'Aion — Una vida, en semanas.').replace('A quiet calendar for a finite life. See your life in weeks, keep the present in view. Free, private, and open source.', 'Un calendario para una vida finita. Mira tu vida en semanas y presta atención al presente. Gratis, privado y de código abierto.'));
await copyFile(new URL('../LICENSE', import.meta.url), new URL('LICENSE.txt', root));

const sourceRevision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: new URL('../', import.meta.url), encoding: 'utf8' }).trim();
const dirty = execFileSync('git', ['status', '--porcelain'], { cwd: new URL('../', import.meta.url), encoding: 'utf8' }).trim().length > 0;
await writeFile(new URL('version.json', root), JSON.stringify({ version: '0.1.0', sourceRevision, dirty }) + '\n');

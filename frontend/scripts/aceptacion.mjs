#!/usr/bin/env node
/**
 * Suite de aceptación de la etapa 1 (change 28, D13; `docs/02-arquitectura.md` §15, §16).
 *
 *   1. Levanta el compose de PRODUCCIÓN como un proyecto aparte (`distribuidora-aceptacion`):
 *      base nueva, HTTPS con la autoridad propia de Caddy y la compilación de producción del
 *      frontend (con su service worker), con `infra/aceptacion.env` (valores solo de prueba).
 *   2. Siembra el escenario (`python -m app.seed --escenario-aceptacion`).
 *   3. Corre Playwright en este equipo contra https://localhost:<puerto>.
 *   4. Descarta el entorno con sus datos (`down -v`), salvo con `--mantener`.
 *
 * Nunca toca el proyecto de desarrollo (`distribuidora`): todo comando de compose lleva
 * `-p distribuidora-aceptacion`. Lo que sigue a `--` o a las opciones propias se pasa a Playwright.
 *
 *   npm run test:e2e                         suite completa
 *   npm run test:e2e:mantener                deja el entorno levantado para mirarlo
 *   npm run test:e2e -- --project=PC         solo la vista de PC
 */
import { spawn } from "node:child_process"
import { mkdirSync, readFileSync, rmSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const PROYECTO = "distribuidora-aceptacion"
const directorioFrontend = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const raiz = path.join(directorioFrontend, "..")
const archivoDeEntorno = "infra/aceptacion.env"
// Solo lo que la suite necesita: Caddy arrastra backend, base y migraciones. Las copias, el backup
// y las tareas periódicas tienen sus propias pruebas y gastan memoria sin aportar acá.
const SERVICIOS = ["caddy"]

const argumentos = process.argv.slice(2)
const mantener = argumentos.includes("--mantener")
const paraPlaywright = argumentos.filter((a) => a !== "--mantener" && a !== "--")

function leerEntorno() {
  const valores = {}
  for (const linea of readFileSync(path.join(raiz, archivoDeEntorno), "utf-8").split(/\r?\n/)) {
    const m = /^([A-Z][A-Z0-9_]*)=(.*)$/.exec(linea.trim())
    if (m) valores[m[1]] = m[2]
  }
  return valores
}

function ejecutar(comando, args, opciones = {}) {
  return new Promise((resolve, reject) => {
    const proceso = spawn(comando, args, { stdio: "inherit", shell: false, cwd: raiz, ...opciones })
    proceso.on("error", reject)
    proceso.on("exit", (codigo) => (codigo === 0 ? resolve(0) : reject(Object.assign(new Error(`${comando} ${args.join(" ")} terminó con código ${codigo}`), { codigo }))))
  })
}

const compose = (...args) => ejecutar("docker", ["compose", "-p", PROYECTO, "-f", "docker-compose.prod.yml", "--env-file", archivoDeEntorno, ...args])

async function descartar() {
  // `-v` borra los volúmenes de ESTE proyecto (la base y los certificados de prueba).
  await compose("down", "-v", "--remove-orphans")
  rmSync(path.join(raiz, ".aceptacion"), { recursive: true, force: true })
}

const entorno = leerEntorno()
const url = `https://${entorno.DOMINIO}:${entorno.CADDY_HTTPS_PORT}`
let codigoFinal = 1

try {
  // Arranque limpio: si quedó un entorno de una corrida anterior, se descarta primero.
  await descartar()
  mkdirSync(path.join(raiz, ".aceptacion", "backups", "bajados"), { recursive: true })
  mkdirSync(path.join(raiz, ".aceptacion", "copia"), { recursive: true })

  await compose("up", "-d", "--build", "--wait", ...SERVICIOS)
  await compose("exec", "-T", "backend", "python", "-m", "app.seed", "--escenario-aceptacion")

  console.log(`\nEntorno de aceptación listo en ${url}\n`)
  const cli = path.join(directorioFrontend, "node_modules", "@playwright", "test", "cli.js")
  try {
    await ejecutar(process.execPath, [cli, "test", ...paraPlaywright], {
      cwd: directorioFrontend,
      env: { ...process.env, ACEPTACION_URL: url },
    })
    codigoFinal = 0
  } catch (error) {
    codigoFinal = error.codigo ?? 1
  }
} catch (error) {
  console.error(`\nNo se pudo preparar el entorno de aceptación: ${error.message}`)
} finally {
  if (mantener) {
    console.log(`\nEntorno dejado levantado en ${url} (usuarios de prueba de la siembra).`)
    console.log(`Para descartarlo: docker compose -p ${PROYECTO} -f docker-compose.prod.yml --env-file ${archivoDeEntorno} down -v`)
  } else {
    await descartar().catch((error) => console.error(`No se pudo descartar el entorno: ${error.message}`))
  }
}
process.exit(codigoFinal)

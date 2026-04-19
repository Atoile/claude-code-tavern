import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const ROOT = path.dirname(fileURLToPath(import.meta.url))

function tavernApiPlugin() {
  return {
    name: 'tavern-api',
    configureServer(server) {
      // Helper to read JSON file safely
      function readJson(filePath) {
        try {
          return JSON.parse(fs.readFileSync(filePath, 'utf8'))
        } catch {
          return null
        }
      }

      // Helper to collect request body
      function collectBody(req) {
        return new Promise((resolve, reject) => {
          let body = ''
          req.on('data', chunk => { body += chunk.toString() })
          req.on('end', () => resolve(body))
          req.on('error', reject)
        })
      }

      server.middlewares.use('/api', async (req, res, next) => {
        const url = new URL(req.url, 'http://localhost')
        const pathname = url.pathname

        res.setHeader('Access-Control-Allow-Origin', '*')
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

        if (req.method === 'OPTIONS') {
          res.writeHead(204)
          res.end()
          return
        }

        // GET /api/queue
        if (req.method === 'GET' && pathname === '/queue') {
          const queuePath = path.join(ROOT, 'infrastructure', 'queue', 'queue.json')
          const data = readJson(queuePath) || []
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(data))
          return
        }

        // POST /api/queue
        if (req.method === 'POST' && pathname === '/queue') {
          try {
            const body = await collectBody(req)
            const queuePath = path.join(ROOT, 'infrastructure', 'queue', 'queue.json')
            fs.mkdirSync(path.dirname(queuePath), { recursive: true })
            fs.writeFileSync(queuePath, body, 'utf8')
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ ok: true }))
          } catch (err) {
            res.writeHead(500)
            res.end(JSON.stringify({ error: err.message }))
          }
          return
        }

        // GET /api/characters
        if (req.method === 'GET' && pathname === '/characters') {
          const charsDir = path.join(ROOT, 'infrastructure', 'characters')
          const result = []
          try {
            const entries = fs.readdirSync(charsDir)
            for (const entry of entries) {
              const dataPath = path.join(charsDir, entry, 'data.json')
              const avatarPath = path.join(charsDir, entry, 'avatar.png')
              if (fs.existsSync(dataPath)) {
                const data = readJson(dataPath)
                if (data) {
                  result.push({
                    id: entry,
                    name: data.meta?.name || entry,
                    dataPath: `infrastructure/characters/${entry}/data.json`,
                    avatarPath: fs.existsSync(avatarPath) ? `infrastructure/characters/${entry}/avatar.png` : null,
                    data
                  })
                }
              }
            }
          } catch {}
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(result))
          return
        }

        // PATCH /api/characters/:id/color
        const colorPatchMatch = pathname.match(/^\/characters\/([^/]+)\/color$/)
        if (req.method === 'PATCH' && colorPatchMatch) {
          try {
            const [, id] = colorPatchMatch
            const body = await collectBody(req)
            const { color } = JSON.parse(body)
            const dataPath = path.join(ROOT, 'infrastructure', 'characters', id, 'data.json')
            const data = readJson(dataPath)
            if (!data) {
              res.writeHead(404)
              res.end(JSON.stringify({ error: 'Character not found' }))
              return
            }
            data.meta = data.meta || {}
            data.meta.color = color || null
            fs.writeFileSync(dataPath, JSON.stringify(data, null, 2), 'utf8')
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ ok: true }))
          } catch (err) {
            res.writeHead(500)
            res.end(JSON.stringify({ error: err.message }))
          }
          return
        }

        // GET /api/raw
        if (req.method === 'GET' && pathname === '/raw') {
          const rawDir = path.join(ROOT, 'infrastructure', 'raw')
          const charsDir = path.join(ROOT, 'infrastructure', 'characters')
          const result = []

          // Build set of source_card filenames from repacked data.json files
          const repackedSourceCards = new Set()
          try {
            for (const entry of fs.readdirSync(charsDir)) {
              const dataPath = path.join(charsDir, entry, 'data.json')
              const data = readJson(dataPath)
              const sourceCard = data?.meta?.source_card
              if (sourceCard) repackedSourceCards.add(sourceCard.toLowerCase())
            }
          } catch {}

          try {
            const entries = fs.readdirSync(rawDir)
            for (const entry of entries) {
              if (!entry.toLowerCase().endsWith('.png')) continue
              if (repackedSourceCards.has(entry.toLowerCase())) continue
              result.push({ filename: entry, path: `infrastructure/raw/${entry}` })
            }
          } catch {}
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(result))
          return
        }

        // GET /api/dialogues — list all dialogues with metadata
        if (req.method === 'GET' && pathname === '/dialogues') {
          const dialoguesDir = path.join(ROOT, 'infrastructure', 'dialogues')
          const result = []
          try {
            for (const entry of fs.readdirSync(dialoguesDir)) {
              const charsPath = path.join(dialoguesDir, entry, 'characters.json')
              const scenarioPath = path.join(dialoguesDir, entry, 'scenario.json')
              const chatPath = path.join(dialoguesDir, entry, 'recent_chat.json')
              if (fs.existsSync(charsPath)) {
                const chars = readJson(charsPath)
                const scenario = readJson(scenarioPath)
                const chat = readJson(chatPath)
                const fullChatPath = path.join(dialoguesDir, entry, 'full_chat.json')
                const statPath = fs.existsSync(fullChatPath) ? fullChatPath : charsPath
                const mtime = fs.statSync(statPath).mtimeMs

                // Extract a representative scenario text from the new participants shape:
                // prefer the leading character's adapted scenario, else the first one.
                let scenario_text = null
                const scenarioParticipants = scenario?.participants || null
                if (scenarioParticipants) {
                  const leadingId = chars?.leading_id
                  scenario_text = scenarioParticipants[leadingId]?.scenario
                    || Object.values(scenarioParticipants)[0]?.scenario
                    || null
                }

                result.push({
                  id: entry,
                  characters: chars,
                  scenario_text,
                  message_count: Array.isArray(chat) ? chat.length : 0,
                  last_updated: mtime
                })
              }
            }
          } catch {}
          result.sort((a, b) => b.last_updated - a.last_updated)
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(result))
          return
        }

        // GET /api/dialogue/:id/:file
        const dialogueGetMatch = pathname.match(/^\/dialogue\/([^/]+)\/([^/]+)$/)
        if (req.method === 'GET' && dialogueGetMatch) {
          const [, id, file] = dialogueGetMatch
          const filePath = path.join(ROOT, 'infrastructure', 'dialogues', id, `${file}.json`)
          const data = readJson(filePath)
          if (data === null) {
            res.writeHead(404)
            res.end(JSON.stringify({ error: 'Not found' }))
          } else {
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(data))
          }
          return
        }

        // DELETE /api/dialogue/:id/:file
        const dialogueDeleteMatch = pathname.match(/^\/dialogue\/([^/]+)\/([^/]+)$/)
        if (req.method === 'DELETE' && dialogueDeleteMatch) {
          try {
            const [, id, file] = dialogueDeleteMatch
            const filePath = path.join(ROOT, 'infrastructure', 'dialogues', id, `${file}.json`)
            if (fs.existsSync(filePath)) fs.unlinkSync(filePath)
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ ok: true }))
          } catch (err) {
            res.writeHead(500)
            res.end(JSON.stringify({ error: err.message }))
          }
          return
        }

        // POST /api/dialogue/:id/:file
        const dialoguePostMatch = pathname.match(/^\/dialogue\/([^/]+)\/([^/]+)$/)
        if (req.method === 'POST' && dialoguePostMatch) {
          try {
            const [, id, file] = dialoguePostMatch
            const body = await collectBody(req)
            const dirPath = path.join(ROOT, 'infrastructure', 'dialogues', id)
            fs.mkdirSync(dirPath, { recursive: true })
            fs.writeFileSync(path.join(dirPath, `${file}.json`), body, 'utf8')
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ ok: true }))
          } catch (err) {
            res.writeHead(500)
            res.end(JSON.stringify({ error: err.message }))
          }
          return
        }

        // GET /api/file-exists?path=...
        if (req.method === 'GET' && pathname === '/file-exists') {
          const filePath = url.searchParams.get('path')
          if (!filePath) {
            res.writeHead(400)
            res.end(JSON.stringify({ error: 'Missing path' }))
            return
          }
          const fullPath = path.join(ROOT, filePath)
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ exists: fs.existsSync(fullPath) }))
          return
        }

        next()
      })

      // Serve character avatars and raw PNGs
      server.middlewares.use('/characters', (req, res, next) => {
        const filePath = path.join(ROOT, 'infrastructure', 'characters', req.url)
        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
          const ext = path.extname(filePath).toLowerCase()
          const mimeTypes = { '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json' }
          res.setHeader('Content-Type', mimeTypes[ext] || 'application/octet-stream')
          fs.createReadStream(filePath).pipe(res)
        } else {
          next()
        }
      })

      server.middlewares.use('/raw', (req, res, next) => {
        const filePath = path.join(ROOT, 'infrastructure', 'raw', req.url)
        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
          res.setHeader('Content-Type', 'image/png')
          fs.createReadStream(filePath).pipe(res)
        } else {
          next()
        }
      })
    }
  }
}

export default defineConfig({
  envPrefix: ['VITE_', 'TAVERN_'],
  plugins: [
    tailwindcss(),
    svelte(),
    tavernApiPlugin()
  ],
  server: {
    host: true,
    fs: {
      allow: ['..']
    },
    watch: {
      ignored: (filePath) => {
        const normalized = filePath.replace(/\\/g, '/')
        return !normalized.includes('/src/')
      }
    }
  }
})

/**
 * End-to-end check of the running product, driven through a real browser.
 *
 * Signs in two users, opens one document in both, and verifies collaboration,
 * AI writing, suggestions and both modes. Requires the backend on :8000 and the
 * dev server on :5173.
 *
 * Usage: node scripts/e2e-check.mjs
 */
import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:5173'
const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` -- ${detail}` : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))


/**
 * Read the document's text without presence UI.
 *
 * Collaboration caret labels render inside the editor DOM, so a raw textContent
 * comparison would differ between clients purely because each sees the other's
 * name. Strip those before comparing.
 */
async function docText(page) {
  return page.evaluate(() => {
    const source = document.querySelector('.coverse-prose')
    if (!source) return ''
    const clone = source.cloneNode(true)
    clone
      .querySelectorAll('.collaboration-carets__label, .collaboration-carets__caret, .suggestion-replacement')
      .forEach((node) => node.remove())
    return (clone.textContent ?? '').trim()
  })
}

// PLAYWRIGHT_CHROMIUM_PATH lets this run against a preinstalled browser
// instead of one Playwright downloads itself.
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined
const browser = await chromium.launch(executablePath ? { executablePath } : {})

async function signIn(name) {
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } })
  const page = await context.newPage()
  page.on('pageerror', (e) => console.log(`  [${name} pageerror] ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error') console.log(`  [${name} console] ${m.text().slice(0,160)}`) })
  await page.goto(BASE)
  await page.fill('input', name)
  await page.click('button[type=submit]')
  await page.waitForSelector('.list-intro', { timeout: 15000 })
  return { context, page }
}

// Alice creates a document.
const alice = await signIn('Alice')
await alice.page.click('button:has-text("New document")')
await alice.page.waitForSelector('.coverse-prose', { timeout: 20000 })
const docUrl = alice.page.url()
check('sign in, create a document, editor mounts', true, docUrl.split('/').pop())

// Alice types.
await alice.page.click('.coverse-prose')
await alice.page.keyboard.type('Alice is writing the opening line.')
await sleep(700)

// Bob opens the same document.
const bob = await signIn('Bob')
await bob.page.goto(docUrl)
await bob.page.waitForSelector('.coverse-prose', { timeout: 20000 })
await bob.page.waitForFunction(
  () => document.querySelector('.coverse-prose')?.textContent?.includes('Alice is writing'),
  { timeout: 15000 },
)
check('Bob sees Alice’s text in real time', true)

// Bob types; Alice sees it.
await bob.page.click('.coverse-prose')
await bob.page.keyboard.press('End')
await bob.page.keyboard.press('Enter')
await bob.page.keyboard.type('Bob adds a second line.')
await alice.page.waitForFunction(
  () => document.querySelector('.coverse-prose')?.textContent?.includes('Bob adds a second line'),
  { timeout: 15000 },
)
check('Alice sees Bob’s text in real time', true)

// Presence: each sees two avatars.
const aliceAvatars = await alice.page.locator('.avatar').count()
check('presence shows both collaborators', aliceAvatars >= 2, `${aliceAvatars} avatars`)

// Remote caret label rendered.
const caret = await alice.page.locator('.collaboration-carets__caret').count()
check('remote collaborator caret is rendered', caret >= 1, `${caret} carets`)

// AI generation from the assistant panel.
await alice.page.click('button:has-text("Assistant")')
await alice.page.waitForSelector('.chat-panel', { timeout: 10000 })
const textBefore = await alice.page.locator('.coverse-prose').textContent()
await alice.page.fill('.chat-composer textarea', 'write a short section about real-time collaboration')
await alice.page.click('.chat-composer button:has-text("Send")')

await alice.page.waitForFunction(
  (before) => (document.querySelector('.coverse-prose')?.textContent ?? '') !== before,
  textBefore,
  { timeout: 30000 },
)
check('AI writes into Alice’s document', true)

// The AI's writing reaches Bob too, through CRDT sync.
await bob.page.waitForFunction(
  (before) => (document.querySelector('.coverse-prose')?.textContent ?? '').length > before.length + 40,
  textBefore,
  { timeout: 30000 },
)
check('AI writing reaches Bob via CRDT sync', true)

// Wait for the generation to settle, then compare both documents.
await alice.page.waitForSelector('.chat-composer button:has-text("Send")', { timeout: 40000 })
await sleep(1200)
const aliceText = await docText(alice.page)
const bobText = await docText(bob.page)
check('both documents converged to identical content', aliceText === bobText,
  `${aliceText?.length} vs ${bobText?.length} chars`)

// The AI produced real structure (a heading node), not literal markdown.
const headings = await alice.page.locator('.coverse-prose h2, .coverse-prose h1').count()
const literalHash = aliceText?.includes('##') ?? false
check('AI output rendered as real nodes, not literal markdown', headings > 0 && !literalHash,
  `${headings} headings`)

await alice.page.screenshot({ path: '/tmp/coverse-e2e-doc-mode.png', fullPage: false })

// Selection rewrite -> suggestion in the rail, body untouched.
const bodyBefore = await docText(alice.page)
/**
 * Select a paragraph and wait for the bubble menu.
 *
 * Retried because the selection occasionally does not take on the first try
 * when a remote collaborator's caret updates land in the same tick. The menu
 * itself is reliable in a single-client flow; this is about the test racing
 * awareness traffic, not about the menu being broken.
 */
let menuShown = false
for (let attempt = 0; attempt < 3 && !menuShown; attempt += 1) {
  await alice.page.locator('.coverse-prose p').first().click()
  await alice.page.keyboard.press('Home')
  await alice.page.keyboard.down('Shift')
  await alice.page.keyboard.press('End')
  await alice.page.keyboard.up('Shift')
  menuShown = await alice.page
    .waitForSelector('.bubble-menu', { timeout: 5000 })
    .then(() => true)
    .catch(() => false)
  if (!menuShown) {
    console.log('  [diag]', JSON.stringify(await alice.page.evaluate(() => ({
      selection: (window.getSelection()?.toString() ?? '').slice(0, 40),
      paragraphs: document.querySelectorAll('.coverse-prose p').length,
      firstParagraph: document.querySelector('.coverse-prose p')?.textContent?.slice(0, 40),
      active: document.activeElement?.className?.slice(0, 50),
      menus: document.querySelectorAll('.bubble-menu').length,
    }))))
  }
}
check('selection bubble menu appears', menuShown)
await alice.page.click('.bubble-menu button:has-text("Rewrite")')
await alice.page.waitForSelector('.rail-card', { timeout: 30000 })
await sleep(800)
const bodyAfter = await docText(alice.page)
check('rewrite creates a suggestion card', await alice.page.locator('.rail-card').count() > 0)
check('rewrite does not modify the document body', bodyBefore === bodyAfter)

// Bob sees the same suggestion: they are collaborative.
const bobCards = await bob.page.locator('.rail-card').count()
check('suggestion is visible to the other collaborator', bobCards > 0, `${bobCards} cards`)

// The in-document ghost text: struck-through original plus the proposal inline.
// This regressed once because extension options are not a live channel to a
// ProseMirror plugin, so it is asserted explicitly.
await alice.page.click('.rail h2')
await sleep(400)
const struck = await alice.page.locator('.suggestion-original').count()
const ghost = await alice.page.locator('.suggestion-replacement').count()
check('inline ghost text renders in the document', struck > 0 && ghost > 0,
  `${struck} struck, ${ghost} ghost`)

await alice.page.screenshot({ path: '/tmp/coverse-e2e-suggestion.png' })

// Accept the rewrite: now the body changes.
await alice.page.click('.rail-card button:has-text("Accept")')
await sleep(900)
const bodyAccepted = await docText(alice.page)
check('accepting a rewrite edits the document', bodyAccepted !== bodyAfter)
let converged = false
for (let i = 0; i < 40 && !converged; i += 1) {
  converged = (await docText(bob.page)) === bodyAccepted
  if (!converged) await sleep(250)
}
check('accepted rewrite propagates to the other client', converged)

// Canvas mode.
await alice.page.click('.mode-toggle button:has-text("Canvas")')
await alice.page.waitForSelector('.canvas-mode', { timeout: 15000 })
check('canvas mode renders chat beside the document', await alice.page.locator('.canvas-mode .chat-panel').count() === 1)
await alice.page.fill('.chat-composer textarea', 'turn this into a product brief')
await alice.page.click('.chat-composer button:has-text("Send")')
await alice.page.waitForSelector('.chat-turn.is-assistant .chat-body', { timeout: 30000 })
await alice.page.waitForFunction(
  () => (document.querySelector('.chat-scroll')?.textContent ?? '').length > 60,
  { timeout: 30000 },
)
check('canvas mode streams a reply into the conversation', true)
await sleep(2500)
await alice.page.screenshot({ path: '/tmp/coverse-e2e-canvas-mode.png' })

await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} browser checks passed`)
process.exit(failed.length ? 1 : 0)

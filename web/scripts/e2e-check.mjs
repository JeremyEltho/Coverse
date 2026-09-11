/**
 * End to end check of the room, driven through real browsers.
 *
 * Puts four people in one room and verifies the things that make it a room
 * rather than four separate chats: one mic, everyone sees the reply arrive, the
 * side chat stays out of the model's context, the shared draft survives a
 * handoff, and anyone can pull the brake.
 *
 * Requires the backend on :8000 and the dev server on :5173.
 * Usage: node scripts/e2e-check.mjs
 */
import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:5173'
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` -- ${detail}` : ''}`)
}

const browser = await chromium.launch(executablePath ? { executablePath } : {})

async function open(name, code) {
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } })
  const page = await context.newPage()
  page.on('pageerror', (e) => console.log(`  [${name}] pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') console.log(`  [${name}] console: ${m.text().slice(0, 140)}`)
  })
  await page.goto(code ? `${BASE}/r/${code}` : BASE)
  return { name, page }
}

const thread = (page) =>
  page.evaluate(() =>
    Array.from(document.querySelectorAll('.turn')).map((t) => ({
      role: t.className.includes('is-assistant') ? 'assistant' : 'user',
      body: t.querySelector('.turn-body')?.textContent?.trim() ?? '',
    })),
  )

// Alice starts the room.
const alice = await open('Alice')
await alice.page.click('button:has-text("Start a room")')
await alice.page.waitForSelector('.landing-card h1:has-text("Join")', { timeout: 15000 })
const code = (await alice.page.locator('.landing-card h1').textContent()).replace('Join ', '').trim()
await alice.page.fill('input', 'Alice')
await alice.page.click('button[type=submit]')
await alice.page.waitForSelector('.room-body', { timeout: 15000 })
check('create a room and join it', true, `code ${code}`)

// The others follow the link.
const others = []
let pickerOptions = 0
for (const [index, name] of ['Bob', 'Cy', 'Dana'].entries()) {
  const person = await open(name, code)
  await person.page.waitForSelector('input', { timeout: 15000 })
  if (index === 0) pickerOptions = await person.page.locator('.sprite-choice').count()
  await person.page.fill('input', name)
  // A different creature each, so the roster reads as four distinct people.
  await person.page.click(`.sprite-choice:nth-child(${index * 3 + 4})`)
  await person.page.click('button[type=submit]')
  await person.page.waitForSelector('.room-body', { timeout: 15000 })
  others.push(person)
}
check('the join screen offers a sprite picker', pickerOptions >= 8, `${pickerOptions} creatures`)
const [bob, cy, dana] = others
await sleep(1200)

const inRoom = await alice.page.locator('.roster .sprite').count()
check('all four people appear in the room', inRoom >= 5,
  `${inRoom} sprites, four people plus the assistant`)

check('the room creator holds the mic',
  (await alice.page.locator('.mic-driver').textContent()).includes('You have the mic'))
check('everyone else is told who has it',
  (await bob.page.locator('.mic-driver').textContent()).includes('Alice'))

// A spectator has no send button.
check('spectators cannot send',
  (await bob.page.locator('.composer-actions button:has-text("Send")').count()) === 0)

// The driver asks, and it streams to all four.
await alice.page.fill('.composer textarea', 'what should we build at this hackathon')
await alice.page.click('.composer-actions button:has-text("Send")')

for (const person of [alice, bob, cy, dana]) {
  await person.page.waitForFunction(
    () => document.querySelectorAll('.turn.is-assistant .turn-body').length > 0,
    { timeout: 25000 },
  )
}
check('the AI reply reaches all four clients', true)

await alice.page.waitForSelector('.composer-actions button:has-text("Send")', { timeout: 30000 })
await sleep(1000)
const threads = await Promise.all([alice, bob, cy, dana].map((p) => thread(p.page)))
check('all four converged on the same thread',
  threads.every((t) => JSON.stringify(t) === JSON.stringify(threads[0])),
  `${threads[0].length} messages`)

check('assistant markdown renders as real elements, not raw syntax',
  (await alice.page.locator('.turn.is-assistant .markdown h2, .turn.is-assistant .markdown ul').count()) > 0 &&
    !(await alice.page.locator('.turn.is-assistant .turn-body').first().textContent()).includes('## '))

await alice.page.screenshot({ path: '/tmp/coverse-room.png' })

// Side chat is for humans only.
await cy.page.click('.rail-tabs button:has-text("Chat")')
await cy.page.fill('.panel-composer input', 'SECRETLINE this direction is weak')
await cy.page.press('.panel-composer input', 'Enter')
await bob.page.click('.rail-tabs button:has-text("Chat")')
await bob.page.waitForSelector('.side-line', { timeout: 10000 })
check('side chat reaches the other humans', true)
check('side chat never enters the AI thread',
  !(await thread(alice.page)).some((t) => t.body.includes('SECRETLINE')))

// A spectator contributes through the queue.
await dana.page.click('.rail-tabs button:has-text("Queue")')
await dana.page.fill('.panel-composer input', 'ask it about offline support')
await dana.page.press('.panel-composer input', 'Enter')
await alice.page.click('.rail-tabs button:has-text("Queue")')
await alice.page.waitForSelector('.queue-card', { timeout: 10000 })
check('a spectator can queue a prompt for the driver', true)

// The shared composer: Bob types into Alice's box.
await bob.page.fill('.composer textarea', 'a half typed thought from Bob')
await alice.page.waitForFunction(
  () => document.querySelector('.composer textarea')?.value.includes('half typed thought'),
  { timeout: 10000 },
)
check('spectators can type into the shared draft', true)

// Mic request, grant, and the draft surviving the handoff.
await bob.page.click('.composer-actions button:has-text("Ask for the mic")')
await alice.page.waitForSelector('.mic-request', { timeout: 10000 })
check('a mic request shows up for the driver', true)

await alice.page.click('.mic-request button:has-text("Hand over")')
await bob.page.waitForFunction(
  () => document.querySelector('.mic-driver')?.textContent?.includes('You have the mic'),
  { timeout: 10000 },
)
check('granting the mic moves it', true)
check('the shared draft survives the handoff',
  (await bob.page.locator('.composer textarea').inputValue()).includes('half typed thought'))
const aliceDemoted = await alice.page
  .waitForFunction(
    () => !document.querySelector('.mic-driver')?.textContent?.includes('You have the mic'),
    { timeout: 10000 },
  )
  .then(() => true)
  .catch(() => false)
check('the old driver loses the send button',
  aliceDemoted &&
    (await alice.page.locator('.composer-actions button:has-text("Send")').count()) === 0)

// Anyone can stop a reply, not just the driver.
await bob.page.fill('.composer textarea', 'write me something really long')
await bob.page.click('.composer-actions button:has-text("Send")')
await dana.page.waitForSelector('.composer-actions button:has-text("Stop")', { timeout: 20000 })
await sleep(250)
await dana.page.click('.composer-actions button:has-text("Stop")')
await sleep(900)
const frozen = (await thread(dana.page)).at(-1).body.length
await sleep(800)
check('any member can stop a running reply',
  (await thread(dana.page)).at(-1).body.length === frozen, `froze at ${frozen} chars`)

// A private question stays private.
await cy.page.click('.rail-tabs button:has-text("Just me")')
const beforeFork = (await thread(alice.page)).length
await cy.page.fill('.panel-composer input', 'quietly explain that last answer')
await cy.page.press('.panel-composer input', 'Enter')
await cy.page.waitForSelector('.fork-turn.is-assistant p', { timeout: 25000 })
await sleep(1500)
check('a private question gets a private answer',
  (await cy.page.locator('.fork-turn.is-assistant p').first().textContent()).length > 10)
check('the private question never touches the shared thread',
  (await thread(alice.page)).length === beforeFork &&
    (await thread(dana.page)).length === beforeFork)

// Pinning is shared, and export produces a file.
await alice.page.locator('.turn.is-assistant').first().hover()
await alice.page.locator('.turn.is-assistant').first().locator('button:has-text("Pin")').click()
await dana.page.click('.rail-tabs button:has-text("Pins")')
await dana.page.waitForSelector('.pin-card', { timeout: 10000 })
check('pinning a reply is visible to everyone', true)

const download = await dana.page
  .waitForEvent('download', { timeout: 10000 })
  .catch(() => null)
  .then(async (d) => d)
const downloadPromise = dana.page.waitForEvent('download', { timeout: 10000 })
await dana.page.click('.panel-composer button:has-text("Export pins")')
const file = download ?? (await downloadPromise.catch(() => null))
check('pins export to a markdown file', file !== null, file ? file.suggestedFilename() : 'no download')

await alice.page.screenshot({ path: '/tmp/coverse-room-full.png' })
await cy.page.screenshot({ path: '/tmp/coverse-room-spectator.png' })

// Sprites: chosen on the way in, and drawn everywhere the person appears.
check('everyone in the room has a sprite in the roster',
  (await alice.page.locator('.roster .sprite').count()) >= 5, 'four people plus the assistant')
check('the mic holder is visibly holding it',
  (await alice.page.locator('.roster-slot.is-holding .mic-glyph').count()) === 1)
check('messages carry their author\'s sprite',
  (await alice.page.locator('.turn .sprite').count()) > 0)

// Typing into the shared draft is presence: everyone else sees who is doing it.
await dana.page.click('.composer textarea')
await dana.page.type('.composer textarea', 'dana typing', { delay: 25 })
const sawTyping = await alice.page
  .waitForFunction(
    () => (document.querySelector('.composer-typing')?.textContent ?? '').includes('typing'),
    { timeout: 8000 },
  )
  .then(() => true)
  .catch(() => false)
check('a typing indicator reaches the other clients', sawTyping)

// And it expires on its own, so a dropped socket cannot leave someone
// permanently typing.
await sleep(3200)
check('the typing indicator clears when they stop',
  (await alice.page.evaluate(
    () => (document.querySelector('.composer-typing')?.textContent ?? '').trim())) === '')
await dana.page.fill('.composer textarea', '')

// The model picker belongs to whoever has the mic.
check('the driver gets a model picker', (await bob.page.locator('.model-trigger').count()) === 1)
check('a spectator sees the model but cannot change it',
  (await cy.page.locator('.model-trigger').count()) === 0 &&
    (await cy.page.locator('.model-label').count()) === 1)

await bob.page.click('.model-trigger')
await bob.page.waitForSelector('.model-menu', { timeout: 10000 })
const allModels = await bob.page.locator('.model-option').count()
await bob.page.fill('.model-search', 'mini')
await sleep(300)
check('the model list filters as you type',
  (await bob.page.locator('.model-option').count()) < allModels, `${allModels} total`)

await bob.page.fill('.model-search', 'Large')
await bob.page.click('.model-option:has-text("Mock Model Large")')
await sleep(700)
check('choosing a model updates the driver',
  (await bob.page.locator('.model-trigger-name').textContent()) === 'Mock Model Large')
await cy.page.waitForFunction(
  () => document.querySelector('.model-label')?.textContent === 'Mock Model Large',
  { timeout: 10000 },
).then(() => check('and every spectator sees the switch', true))
 .catch(() => check('and every spectator sees the switch', false))

// A room that is gone must say so. Retrying forever would leave people staring
// at "reconnecting" for something that is never coming back.
const ghost = await open('Ghost', 'ZZZZZZ')
await ghost.page.waitForSelector('.error-banner', { timeout: 10000 })
check('joining a room that does not exist explains itself', true)

const stale = await open('Stale', code)
await stale.page.evaluate((c) => {
  sessionStorage.setItem(
    'coverse.member',
    JSON.stringify({
      code: c,
      member: {
        code: c,
        member_id: 'not-a-real-member',
        name: 'Stale',
        color: '#000',
        is_driver: false,
      },
    }),
  )
}, code)
await stale.page.reload()
await stale.page.waitForSelector('.landing-card h1', { timeout: 15000 })
check('a stale seat is explained rather than spinning forever',
  /not in this room|ended/i.test(await stale.page.locator('.landing-card h1').textContent()))
check('and offers a way back in',
  (await stale.page.locator('button:has-text("Try joining")').count()) > 0)

// A phone cannot drive, but it must be able to watch and talk.
const phoneContext = await browser.newContext({
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
})
const phone = await phoneContext.newPage()
await phone.goto(`${BASE}/r/${code}`)
await phone.waitForSelector('input', { timeout: 15000 })
await phone.fill('input', 'Phone')
await phone.click('button[type=submit]')
await phone.waitForSelector('.room-body', { timeout: 15000 })
await sleep(800)

const overflow = await phone.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
)
check('no horizontal overflow on a phone', overflow <= 0, `${overflow}px`)
check('a phone can read the thread', (await phone.locator('.turn').count()) > 0)

await phone.click('.rail-tabs button:has-text("Chat")')
await phone.fill('.panel-composer input', 'watching from my phone')
await phone.press('.panel-composer input', 'Enter')
await bob.page.click('.rail-tabs button:has-text("Chat")')
await bob.page.waitForFunction(
  () => document.body.textContent?.includes('watching from my phone'),
  { timeout: 10000 },
)
check('a phone spectator can use the side chat', true)
await phone.screenshot({ path: '/tmp/coverse-phone.png' })

await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} browser checks passed`)
process.exit(failed.length ? 1 : 0)

import { expect, mock, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'
import type { On } from 'claude-code'

// the test runner has timers; the hooks environment's typings do not declare them
declare const setTimeout: (fn: (value?: unknown) => void, ms: number) => unknown
declare const h: (type: unknown, props: unknown, ...children: unknown[]) => never

const STATE = (over = {}) =>
  JSON.stringify({ ai: true, research: true, auto_open: true, session: 's1', entries: [], patterns: [], skill: null, notice: null, ...over })

function world(on: On, opts: { os?: string; out?: string; exit?: number; box?: string; refused?: boolean } = {}) {
  const opened: string[] = []
  const ran: string[][] = []
  const fills: { text: string; mode?: string; decorations?: unknown[] }[] = []
  const submits: string[] = []
  const stdins: (string | undefined)[] = []
  mock.env(on, opts.os ? { OS: opts.os } : {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('session.attach', ($, e) => ({ clientId: e.clientId }))
  on('clock.now', () => ({ value: 0 }))
  on('prompt.submit', ($, e) => (submits.push(e.text), { text: e.text }))
  on('prompt.read', () => ({ value: { text: opts.box ?? '', cursor: 0 } }))
  on('prompt.fill', ($, e) => {
    if (opts.refused) return { isFilled: false }
    fills.push({ text: e.text, mode: e.mode, decorations: (e as { decorations?: unknown[] }).decorations })
    return { isFilled: true }
  })
  on('turn.complete', () => ({ text: '' }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [] }))
  on('ui.open', ($, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    stdins.push(e.init?.stdin)
    const version = e.argv.includes('--version')
    return {
      value: {
        exitCode: version ? 0 : (opts.exit ?? 0),
        stdout: version ? 'Python 3.13.0' : (opts.out ?? STATE()),
        stderr: opts.exit ? 'Traceback\nboom' : '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  return { opened, ran, fills, submits, stdins }
}

const START = { cwd: '/w', surface: 'terminal', isInteractive: true } as const
// session.start leaves its pane.py run in the background (the first prompt never waits for it): let it finish
const settle = () => new Promise(r => setTimeout(r, 50))

test('opens the pane at session start on macOS', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  expect(w.opened).toEqual(['coachline'])
  expect(w.ran.some(a => a.includes('--json') && a.includes('s1'))).toBe(true)
})

test('does nothing on Windows', async ($, on) => {
  const w = world(on, { os: 'Windows_NT' })
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('skips headless sessions', async ($, on) => {
  const w = world(on)
  await $.session.start({ ...START, surface: null, isInteractive: false })
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('does not open when auto-open is off', async ($, on) => {
  const w = world(on, { out: STATE({ auto_open: false }) })
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual([])
})

test('opens again on a prompt while the pane is not placed', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual(['coachline', 'coachline'])
})

const ENTRY = {
  key: 'k1', stamp: '15:28', glyph: '!', state: 'local', words: 'can be improved', text: 'make the shoe site premium', after: '',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · ! can be improved', null], ['prompt', 'prompt', 'make the shoe site premium', '', null]],
}

test('keeps the last good state when pane.py fails', async ($, on) => {
  let exit = 0
  mock.env(on, {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('clock.now', () => ({ value: 0 }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [{ id: 'coachline', title: 'coachline', isShown: true, isFocused: false, isPlaced: true }] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => ({
    value: {
      exitCode: e.argv.includes('--version') ? 0 : exit,
      stdout: e.argv.includes('--version') ? 'Python 3.13.0' : STATE({ entries: [ENTRY] }),
      stderr: exit ? 'Traceback\nboom' : '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))
  await $.session.start(START)
  await settle()
  exit = 1
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect(await ui.find({ text: /make the shoe site premium/ })).toBeDefined()
  expect(await ui.find({ text: /boom · run \/coach doctor/ })).toBeDefined()
})

const SUBMIT = { text: 'hi', wait: false, origin: { kind: 'composer' } } as const
const RESULT = (stdout: string, exitCode = 0) => ({
  value: { exitCode, stdout, stderr: exitCode ? 'boom' : '', isStdoutTruncated: false, isStderrTruncated: false },
})

function base(on: On, clock = true) {
  mock.env(on, {})
  if (clock) on('clock.now', () => ({ value: 0 }))
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [] }))
}

test('runs one pane.py at a time and catches up once afterwards', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let running = 0
  let most = 0
  let runs = 0
  on('process.run', async ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    if (!e.argv.includes('--json')) return RESULT('')          // outcome reports run on their own: this is about refreshes
    runs += 1
    running += 1
    most = Math.max(most, running)
    await Promise.resolve()
    await Promise.resolve()
    running -= 1
    return RESULT(STATE())
  })
  await $.session.start(START)
  await settle()
  await Promise.all([$.prompt.submit(SUBMIT), $.prompt.submit(SUBMIT), $.prompt.submit(SUBMIT)])
  await settle()
  expect(most).toBe(1)
  expect(runs).toBeLessThanOrEqual(3)
})

test('opens the pane even without Python, so its error can be read', async ($, on) => {
  base(on)
  const opened: string[] = []
  on('ui.open', ($, e) => { opened.push(e.id); return { value: { isPlaced: true } } })
  on('process.run', () => { throw new Error('not found') })
  await $.session.start(START)
  await settle()
  expect(opened).toEqual(['coachline'])
})

test('asks for Python once, not on every prompt', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let asked = 0
  on('process.run', ($, e) => {
    if (e.argv.includes('--version')) asked += 1
    throw new Error('not found')
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  await $.prompt.submit(SUBMIT)
  expect(asked).toBe(3)          // python3, python, then py -3; never again this session
})

test('falls back to py -3 where python3 and python are missing or the Store stand-ins', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv[0] === 'python3') throw new Error('not found')
    if (e.argv[0] === 'python') return RESULT('', 9009)           // the Microsoft Store alias: no Python, a failing exit
    return RESULT(e.argv.includes('--version') ? 'Python 3.13.0' : STATE())
  })
  await $.session.start(START)
  await settle()
  expect(ran.find(a => a.some(x => x.endsWith('/scripts/pane.py')))?.slice(0, 2)).toEqual(['py', '-3'])
})

test('session start does not wait for pane.py', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let release: () => void = () => {}
  const held = new Promise<void>(r => { release = r })
  on('process.run', async ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    await held
    return RESULT(STATE())
  })
  let started = false
  const start = $.session.start(START).then(() => { started = true })
  await Promise.race([start, new Promise(r => setTimeout(r, 200))])
  expect(started).toBe(true)
  release()
  await settle()
})

const NO_ANSWER = {
  ...ENTRY, glyph: '×', state: 'error', words: 'no answer yet, press e to retry',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · × no answer yet', null], ['prompt', 'prompt', 'make the shoe site premium', '', null]],
}

test('Analyse is there whenever there is no enhanced prompt, and it names the session', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(e.argv.includes('--enhance') ? 'asking Claude' : STATE({ entries: [NO_ANSWER] }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'analyse' })
  const enhance = ran.find(a => a.includes('--enhance'))
  expect(enhance).toBeDefined()
  expect(enhance?.slice(-4)).toEqual(['--enhance', 'k1', '--session', 's1'])
})

const WITH_WEB = {
  ...ENTRY, glyph: '✓', state: 'done', words: 'analysed', after: 'Do it.\n\nReferences (checked links from web research):\n- Use GreatKit: https://x.example.com/g',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · ✓ analysed', null], ['web', 'better', '1. better: GreatKit (tool) - w', '', null],
          ['web', 'itemacts', '', '', 'item:x.example.com/g']],
}

test('Hide, I use this and Look again call pane.py with the item and the prompt', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(e.argv.includes('--mark') || e.argv.includes('--research') ? 'ok' : STATE({ entries: [WITH_WEB] }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'hide:x.example.com/g' })
  await ui.press({ key: 'use:x.example.com/g' })
  await ui.press({ key: 'research' })
  const tail = (flag: string) => ran.find(a => a.includes(flag))?.slice(-3)
  expect(tail('dismissed')).toEqual(['--mark', 'dismissed', 'x.example.com/g'])
  expect(tail('adopted')).toEqual(['--mark', 'adopted', 'x.example.com/g'])
  expect(ran.find(a => a.includes('--research'))?.slice(-4)).toEqual(['--research', 'k1', '--session', 's1'])
})

test('Look again is not offered while web research is off', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(STATE({ entries: [WITH_WEB], research: false }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  let pressed = true
  try {
    await ui.press({ key: 'research' })
  } catch {
    pressed = false
  }
  expect(pressed).toBe(false)
  expect(ran.some(a => a.includes('--research'))).toBe(false)
})

test('each section of the card is a rounded box in its colour, a web find named on its own line', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => (e.argv.includes('--version') ? RESULT('Python 3.13.0') : RESULT(STATE({ entries: [WITH_WEB] }))))
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect((await ui.find({ key: 's0' }))?.props).toMatchObject({ borderStyle: 'round', borderColor: 'whiteBright' })
  expect((await ui.find({ key: 's1' }))?.props).toMatchObject({ borderStyle: 'round', borderColor: 'magentaBright' })
  expect((await ui.find({ type: 'Text', text: /^Your prompt$/ }))?.props).toMatchObject({ bold: true, color: 'whiteBright' })
  expect((await ui.find({ type: 'Text', text: /^GreatKit$/ }))?.props).toMatchObject({ bold: true })
  expect(await ui.find({ type: 'Text', text: /^w$/ })).toBeDefined()
})

test('the terminal pane names coachline in the coral accent', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => (e.argv.includes('--version') ? RESULT('Python 3.13.0') : RESULT(STATE({ entries: [WITH_WEB] }))))
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect((await ui.find({ type: 'Text', text: /^coachline$/ }))?.props).toMatchObject({ bold: true, color: '#E8735A' })
})

test('keeps checking while web research is under way, then stops', async ($, on) => {
  base(on, false)
  const clock = mock.clock(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let researching = true
  let runs = 0
  on('process.run', ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    runs += 1
    return RESULT(STATE({ entries: [{ ...ENTRY, state: 'done' }], researching }))
  })
  await $.session.start(START)
  await clock.settle()
  const before = runs
  await clock.advance(3000)
  expect(runs).toBeGreaterThan(before)                // the analysis is in, the web finds are not: still checking
  researching = false
  await clock.advance(3000)
  const after = runs
  await clock.advance(9000)
  expect(runs).toBe(after)                            // the finds are in: no more checks until the next prompt or turn
})

// An editor's session (the VS Code extension's) runs the prompt.submit hooks before the prompt is in its transcript, where
// coachline reads it: the pane checks again until it is, for a minute at most
test('after a prompt it keeps checking until the prompt shows, then stops', async ($, on) => {
  base(on, false)
  const clock = mock.clock(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let written = false
  let runs = 0
  on('process.run', ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    runs += 1
    return RESULT(STATE({ entries: written ? [{ ...ENTRY, state: 'done' }] : [] }))
  })
  await $.session.start(START)
  await clock.settle()
  await $.prompt.submit(SUBMIT)
  await clock.settle()
  const before = runs
  await clock.advance(3000)
  expect(runs).toBeGreaterThan(before)                // not in yet: still checking
  written = true
  await clock.advance(3000)
  const after = runs
  await clock.advance(9000)
  expect(runs).toBe(after)                            // in: no more checks
})

test('a prompt that never shows is waited for a minute, no longer', async ($, on) => {
  base(on, false)
  const clock = mock.clock(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let runs = 0
  on('process.run', ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    runs += 1
    return RESULT(STATE())
  })
  await $.session.start(START)
  await clock.settle()
  await $.prompt.submit(SUBMIT)
  await clock.settle()
  await clock.advance(63000)
  const after = runs
  await clock.advance(9000)
  expect(runs).toBe(after)
})

// What a session the Claude desktop app runs gets, as checked in the app (2.42304): an SDK host's start, no surface and not
// interactive, then the app attaching. Its first prompt comes before the attach.
const DESKTOP_START = { cwd: '/w', surface: null, isInteractive: false } as const
const ATTACH = { surface: 'desktop', clientId: 'desktop-1', viewport: { columns: 106, rows: 47, isFullscreen: true } } as const
// the editors' Claude Code extension (VS Code, and the same extension in Cursor, Windsurf, Antigravity) attaches as `vscode`
const EDITOR = { surface: 'vscode', clientId: 'vscode-1', viewport: { columns: 60, rows: 40, isFullscreen: true } } as const

const CARD = {
  ...WITH_WEB,
  lines: [
    ['prompt', 'head', 'Your prompt', '15:28 · ✓ analysed', null], ['prompt', 'prompt', 'make the shoe site premium', '', null],
    ['', 'blank', '', '', null], ['improve', 'head', 'Improve', 'frontend', null], ['improve', 'blue', '• Name the look you want', '', null],
    ['', 'blank', '', '', null], ['enh', 'head', 'Enhanced prompt', 'c Copy', 'copy'], ['enh', 'enh', 'Do it.', '', null],
    ['enh', 'enh', '', '', null], ['enh', 'bluedim', 'Includes references from web research.', '', null],
    ['', 'blank', '', '', null], ['web', 'head', 'Worth a look', 'found on the web, not installed', null],
    ['web', 'better', '1. better: GreatKit (tool) - w', '', null], ['web', 'src', '   https://x.example.com/g', '', null],
    ['web', 'itemacts', '', '', 'item:x.example.com/g'],
  ],
}

async function desktopSession($: Parameters<TestBody>[0], on: On, os?: string, attach: typeof ATTACH | typeof EDITOR = ATTACH) {
  const w = world(on, { os, out: STATE({ entries: [CARD] }) })
  await $.session.start(DESKTOP_START)
  await $.prompt.submit(SUBMIT)
  await settle()
  const before = [...w.opened]
  await $.session.attach(attach)
  await settle()
  return { ...w, before }
}

test('the desktop app on macOS: the pane opens when the app attaches', async ($, on) => {
  const w = await desktopSession($, on)
  expect(w.before).toEqual([])
  expect(w.opened).toEqual(['coachline'])
  expect(w.ran.some(a => a.includes('--json') && a.includes('s1'))).toBe(true)
})

test('the desktop app on Windows: the pane opens too (only the Windows terminal has the separate panel)', async ($, on) => {
  const w = await desktopSession($, on, 'Windows_NT')
  expect(w.opened).toEqual(['coachline'])
})

test('a reload in a desktop session finds the app attached and keeps the pane going', async ($, on) => {
  const w = world(on, { os: 'Windows_NT' })
  on('session.surfaces', () => ({ value: ['desktop'] }))
  await $.session.start(DESKTOP_START)
  await settle()
  expect(w.opened).toEqual(['coachline'])
})

test('a phone attaching to a -p run does not start the pane', async ($, on) => {
  const w = world(on)
  await $.session.start(DESKTOP_START)
  await $.session.attach({ surface: 'mobile', clientId: 'mobile-1' })
  await settle()
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

// the desktop's colours: theme keys, which follow its light and dark themes. ANSI names are fixed colours there (white on white)
const THEME = ['text', 'suggestion', 'claude', 'skill', 'success', 'inactive', 'error', undefined]
const ANSI = /^(black|red|green|yellow|blue|magenta|cyan|white|gray|grey)(Bright)?$/

test('on the desktop the card follows the app: its own cards, theme colours, native buttons', async ($, on) => {
  await desktopSession($, on, 'Windows_NT')
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'desktop', component: 'Pane', requestId: 'coachline', props: {} as never })
  // the app's own card: a neutral rounded border (no colour of ours); your prompt on the surface of your own messages
  expect((await ui.find({ key: 's0' }))?.props).toMatchObject({ borderStyle: 'round', backgroundColor: 'userMessageBackground' })
  for (const key of ['s1', 's2', 's3']) {
    const p = (await ui.find({ key }))?.props
    expect(p).toMatchObject({ borderStyle: 'round' })
    expect(p?.borderColor).toBeUndefined()
  }
  // one accent per section, on its small title
  const title = async (t: string) => (await ui.find({ type: 'Text', text: new RegExp(`^${t}$`) }))?.props
  expect(await title('Your prompt')).toMatchObject({ size: 'footnote', weight: 'semibold', color: 'text' })
  expect(await title('Improve')).toMatchObject({ color: 'suggestion' })
  expect(await title('Enhanced prompt')).toMatchObject({ color: 'claude' })
  expect(await title('Worth a look')).toMatchObject({ color: 'skill' })
  for (const t of await ui.findAll({ type: 'Text' })) {
    expect(THEME).toContain(t.props.color)
    expect(String(t.props.color ?? '')).not.toMatch(ANSI)
  }
  expect((await ui.find({ type: 'Button', key: 'copy' }))?.props).toMatchObject({ variant: 'primary' })
  // a blank line of the enhanced prompt keeps its height, where an empty Text has none
  expect(await ui.find({ type: 'Text', text: /^ $/ })).toBeDefined()
})

test('the terminal keeps its colours and boxes', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => (e.argv.includes('--version') ? RESULT('Python 3.13.0') : RESULT(STATE({ entries: [CARD] }))))
  await $.session.start(START)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect((await ui.find({ key: 's0' }))?.props).toMatchObject({ borderStyle: 'round', borderColor: 'whiteBright', paddingX: 1 })
  expect((await ui.find({ key: 's1' }))?.props).toMatchObject({ borderColor: 'blueBright' })
  expect((await ui.find({ key: 's2' }))?.props).toMatchObject({ borderColor: 'cyanBright' })
  expect((await ui.find({ type: 'Text', text: /^Enhanced prompt$/ }))?.props).toMatchObject({ bold: true, color: 'cyanBright' })
  expect((await ui.find({ type: 'Button', key: 'copy' }))?.props.variant).toBeUndefined()
})

test('Copy on the desktop copies there', async ($, on) => {
  const copies: unknown[] = []
  on('ui.copy', ($, e) => {
    copies.push({ ...e })
    return { value: { isCopied: true } }
  })
  await desktopSession($, on)
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'desktop', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'copy' })
  expect(copies).toEqual([{ text: CARD.after, surface: 'desktop' }])
})

test('an editor (VS Code, Cursor, Windsurf, Antigravity) opens the pane when its Claude Code extension attaches', async ($, on) => {
  const w = await desktopSession($, on, 'Windows_NT', EDITOR)
  expect(w.before).toEqual([])
  expect(w.opened).toEqual(['coachline'])
})

test('a reload in an editor session finds the extension attached and keeps the pane going', async ($, on) => {
  const w = world(on)
  on('session.surfaces', () => ({ value: ['vscode'] }))
  await $.session.start(DESKTOP_START)
  await settle()
  expect(w.opened).toEqual(['coachline'])
})

// what the editor's webview paints: its theme's variables for these keys, its terminal palette for an ANSI name
const EDITOR_THEME = ['text', 'suggestion', 'claude', 'magenta', 'success', 'inactive', 'error', undefined]

test('in an editor the card follows its theme: its own cards padded in cells, theme colours, spacing in cells', async ($, on) => {
  await desktopSession($, on, undefined, EDITOR)
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'vscode', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect((await ui.find({ key: 's0' }))?.props).toMatchObject({ borderStyle: 'round', backgroundColor: 'userMessageBackground', paddingX: 1 })
  for (const key of ['s1', 's2', 's3']) {
    const p = (await ui.find({ key }))?.props
    expect(p).toMatchObject({ borderStyle: 'round', paddingX: 1 })
    expect(p?.borderColor).toBeUndefined()
  }
  const title = async (t: string) => (await ui.find({ type: 'Text', text: new RegExp(`^${t}$`) }))?.props
  expect(await title('Your prompt')).toMatchObject({ bold: true, color: 'text' })   // an editor draws no weight, only bold
  expect(await title('Improve')).toMatchObject({ color: 'suggestion' })
  expect(await title('Enhanced prompt')).toMatchObject({ color: 'claude' })
  expect(await title('Worth a look')).toMatchObject({ color: 'magenta' })            // it has no `skill` key
  for (const t of await ui.findAll({ type: 'Text' })) expect(EDITOR_THEME).toContain(t.props.color)
  // an editor reads spacing in cells; a step name ('sm') is dropped there
  for (const b of await ui.findAll({ type: 'Box' })) {
    for (const k of ['gap', 'marginTop', 'paddingX', 'paddingY']) expect(['number', 'undefined']).toContain(typeof b.props[k])
  }
  expect((await ui.find({ type: 'Button', key: 'copy' }))?.props).toMatchObject({ variant: 'primary' })
  // an editor wraps a row Box unless told not to: a bullet's dot would sit on a line of its own
  for (const b of await ui.findAll({ type: 'Box' })) {
    if ((b.props.flexDirection ?? 'row') === 'row') expect(b.props.flexWrap).toBe('nowrap')
  }
})

test('Copy in an editor copies there', async ($, on) => {
  const copies: unknown[] = []
  on('ui.copy', ($, e) => {
    copies.push({ ...e })
    return { value: { isCopied: true } }
  })
  await desktopSession($, on, undefined, EDITOR)
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'vscode', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'copy' })
  expect(copies).toEqual([{ text: CARD.after, surface: 'vscode' }])
})

// Parity: each surface draws the card in its own design, but a person reads the same words and has the same buttons, in the
// same order, and each button does the same. A thread with every kind of card: analysed with web finds, failed, a long prompt
const LONG = {
  ...ENTRY, key: 'k3', stamp: '15:30', text: 'premium '.repeat(200).trim(),
  lines: [['prompt', 'head', 'Your prompt', '15:30 · ! can be improved', null], ['prompt', 'prompt', 'premium premium…', '', null],
          ['prompt', 'meta', 'Enter shows the whole prompt', '', 'enter'], ['', 'blank', '', '', null],
          ['improve', 'head', 'Improve', '', null], ['improve', 'blue', '• Say what premium means here', '', null]],
}
const THREAD = STATE({ entries: [CARD, NO_ANSWER, LONG], patterns: ['You ask for premium without saying what it means.'], skill: 'tidy-hero' })
const SURFACES = ['terminal', 'desktop', 'vscode'] as const

// the words a person reads and the buttons' labels, in order; the terminal's header names the pane, an app's title bar does
async function shown(ui: { findAll: (q: { type?: string }) => Promise<{ type: string; props: Record<string, unknown>; text: string }[]> }) {
  const out: string[] = []
  for (const el of await ui.findAll({})) {
    if (el.type === 'Button') out.push(`[${String(el.props.label).slice(0, 40)}]`)
    // the terminal names the pane in its header (an app does in its title bar): its own Text, in the accent
    else if (el.type === 'Text' && el.text.trim() && el.text.trim() !== 'coachline') out.push(el.text.trim().replace(/^· this thread/, 'This thread'))
  }
  return out
}

// each prompt picked from the list, the patterns opened, the whole long prompt shown; and back
const VIEWS: [string, string[], string[]][] = [
  ['first prompt', ['e0'], []], ['second prompt', ['e1'], []], ['third prompt', ['e2'], []],
  ['patterns', ['patterns'], ['patterns']], ['whole prompt', ['e2', 'whole'], ['less']], ['library', ['library'], ['library']],
]

test('every surface shows the same words and buttons', async ($, on) => {
  world(on, { out: THREAD })
  await $.session.start(START)
  await settle()
  for (const [view, go, back] of VIEWS) {
    const seen: Record<string, string[]> = {}
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'coachline', surface, component: 'Pane', requestId: 'coachline', props: {} as never })
      for (const key of go) await ui.press({ key })
      seen[surface] = [view, ...(await shown(ui)), ...(await ui.findAll({ type: 'Button' })).map(b => `key ${b.key}`)]
      for (const key of back) await ui.press({ key })
      await ui.unmount()
    }
    expect(seen.desktop).toEqual(seen.terminal)
    expect(seen.vscode).toEqual(seen.terminal)
  }
})

test('every button does the same on every surface', async ($, on) => {
  const w = world(on, { out: THREAD })
  const copies: { text: string; surface?: string }[] = []
  on('ui.copy', ($, e) => {
    copies.push({ text: e.text, surface: e.surface })
    return { value: { isCopied: true } }
  })
  await $.session.start(START)
  await settle()
  const did: Record<string, string[]> = {}
  for (const surface of SURFACES) {
    did[surface] = []
    for (const [view, go, back] of VIEWS) {
      const ui = await $.ui.mount({ plugin: 'coachline', surface, component: 'Pane', requestId: 'coachline', props: {} as never })
      for (const key of go) await ui.press({ key })
      for (const b of await ui.findAll({ type: 'Button' })) {
        if (!b.key || /^e\d+$|^(patterns|whole|less|library)$/.test(b.key)) continue    // they change the view, which the test above follows
        w.ran.length = 0
        copies.length = 0
        w.fills.length = 0
        await ui.press({ key: b.key })
        await settle()
        const runs = w.ran.filter(a => !a.includes('--json') && !a.includes('--version')).map(a => a.slice(2).join(' '))
        const copied = copies.map(c => `copied ${c.text.length} characters ${c.surface === surface ? 'here' : `on ${c.surface}`}`)
        const filled = w.fills.map(f => `filled ${f.text.length} characters`)
        did[surface].push(`${view} ${b.key}: ${[...runs, ...copied, ...filled].join(', ')}`)
      }
      for (const key of back) await ui.press({ key })
      await ui.unmount()
    }
  }
  expect(did.terminal).toContain(`first prompt copy: copied ${CARD.after.length} characters here`)
  expect(did.terminal).toContain(`first prompt use: filled ${CARD.after.length} characters`)
  expect(did.terminal).toContain('second prompt analyse: --enhance k1 --session s1')
  expect(did.terminal).toContain('patterns skill: --install tidy-hero')
  expect(did.desktop).toEqual(did.terminal)
  expect(did.vscode).toEqual(did.terminal)
})

// the hint under the prompt box: the draft scored by pane.py --score, drawn as PromptHint's tail
function hinting(on: On, opts: { os?: string; draft?: () => string; score?: (draft: string) => object; fail?: boolean; hints?: boolean; hold?: Promise<void>[];
  holding?: boolean; refuse?: boolean } = {}) {
  mock.env(on, opts.os ? { OS: opts.os } : {})
  const clock = mock.clock(on)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('prompt.read', () => ({ value: { text: (opts.draft ?? (() => 'fix it now please'))(), cursor: 0 } }))
  const scored: string[] = []
  const sent: string[] = []
  const filled: string[] = []
  on('prompt.submit', ($, e) => (sent.push(e.text), { text: e.text }))
  on('prompt.fill', ($, e) => (opts.refuse ? { isFilled: false } : (filled.push(e.text), { isFilled: true })))
  on('prompt.change', ($, e) => ({ text: e.text }))
  on('process.run', async ($, e) => {
    const score = e.argv.includes('--score')
    if (score) scored.push(e.init?.stdin ?? '')
    if (score && opts.hold?.length) await opts.hold.shift()                     // a slow Python: this answer waits for the test
    const out = e.argv.includes('--version') ? 'Python 3.13.0'
      : score ? JSON.stringify((opts.score ?? (() => ({ meter: '▰▱▱▱▱', hint: 'name a file, function, error or number', words: 4, hold: !!opts.holding })))(e.init?.stdin ?? ''))
      : STATE({ hints: opts.hints ?? true })
    return { value: { exitCode: score && opts.fail ? 1 : 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  const tails: (string | undefined)[] = []
  // the engine's own line, beneath the plugin: it records the tail it is handed
  on('ui.render', ($, e) => {
    if ((e as { component?: string }).component === 'PromptHint') tails.push((e.props as { tail?: string }).tail)
    const { Text } = $.ui.resolve(e)
    return h(Text, null, 'line')
  })
  return { clock, scored, tails, sent, filled }
}
const HINT = { isDraft: true, isWorking: false, hint: '? for shortcuts' }
const draw = async ($: Parameters<TestBody>[0], props = HINT) => {
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'PromptHint', props } as never)
  await ui.unmount()
}

for (const os of ['', 'Windows_NT']) {
  test(`a pause in typing shows the meter and what the draft lacks under the prompt${os ? ' (Windows)' : ''}`, async ($, on) => {
    const w = hinting(on, { os })
    await $.session.start(START)
    await draw($)
    expect(w.scored).toEqual([])
    await w.clock.advance(600)
    await draw($)
    expect(w.scored).toEqual(['fix it now please'])
    expect(w.tails.at(-1)).toBe('· ▰▱▱▱▱  name a file, function, error or number')
  })
}

test('typing on within the pause scores once, after the last edit', async ($, on) => {
  let draft = 'fix'
  const w = hinting(on, { draft: () => draft })
  await $.session.start(START)
  await draw($)
  await w.clock.advance(100)
  draft = 'fix it now please'
  await draw($)
  await w.clock.advance(600)
  expect(w.scored).toEqual(['fix it now please'])
})

test('a score for an older draft is never drawn over a newer one', async ($, on) => {
  let draft = 'fix it now please'
  const w = hinting(on, { draft: () => draft })
  await $.session.start(START)
  await draw($)
  await w.clock.advance(600)
  draft = 'fix it now please, the login page'
  await draw($)
  expect(w.tails.at(-1)).toBeUndefined()
})

test('no hint while Claude works or when pane.py fails', async ($, on) => {
  const w = hinting(on, { fail: true })
  await $.session.start(START)
  await draw($)
  await w.clock.advance(600)
  await draw($)
  expect(w.tails.at(-1)).toBeUndefined()
  await draw($, { ...HINT, isWorking: true })
  expect(w.tails.at(-1)).toBeUndefined()
})

test('hints off: the draft is never scored', async ($, on) => {
  const w = hinting(on, { hints: false })
  await $.session.start(START)
  await draw($)
  await w.clock.advance(600)
  await draw($)
  expect(w.scored).toEqual([])
  expect(w.tails.at(-1)).toBeUndefined()
})

// Use: the enhanced prompt into the prompt box, never sent (Q7)
const ASKING = { ...CARD, after: 'Make the [ASK: which page?] faster. Done when p95 < 300ms.' }
async function pressUse($: Parameters<TestBody>[0], surface: 'terminal' | 'desktop' | 'vscode' = 'terminal') {
  const ui = await $.ui.mount({ plugin: 'coachline', surface, component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'use' })
  return ui
}

test('Use puts the enhanced prompt in an empty prompt box, its [ASK] gaps in bold, and sends nothing', async ($, on) => {
  const w = world(on, { out: STATE({ entries: [ASKING] }) })
  await $.session.start(START)
  await settle()
  const ui = await pressUse($)
  const at = ASKING.after.indexOf('[ASK')
  expect(w.fills).toEqual([{ text: ASKING.after, mode: 'replace', decorations: [{ start: at, end: at + '[ASK: which page?]'.length, bold: true }] }])
  expect(w.submits).toEqual([])
  expect(await ui.find({ type: 'Text', text: /in your prompt box: fill the \[ASK\] parts, then send/ })).toBeDefined()
  await ui.unmount()
})

test('Use asks before it replaces a draft in the box', async ($, on) => {
  const w = world(on, { out: STATE({ entries: [ASKING] }), box: 'half typed' })
  await $.session.start(START)
  await settle()
  const ui = await pressUse($)
  expect(w.fills).toEqual([])
  expect(await ui.find({ type: 'Text', text: /your prompt box has a draft: press Use again to replace it/ })).toBeDefined()
  await ui.press({ key: 'use' })
  expect(w.fills.length).toBe(1)
  await ui.unmount()
})

test('Use copies when the box does not take it, whatever the cause', async ($, on) => {
  const copies: string[] = []
  const w = world(on, { out: STATE({ entries: [ASKING] }), refused: true })
  on('ui.copy', ($, e) => (copies.push(e.text), { value: { isCopied: true } }))
  await $.session.start(START)
  await settle()
  const ui = await pressUse($)
  expect(copies).toEqual([ASKING.after])
  expect(await ui.find({ type: 'Text', text: /copied instead: the prompt box did not take it/ })).toBeDefined()
  expect(w.submits).toEqual([])
  await ui.unmount()
})

test('a draft typed while an older one is being scored is scored next', async ($, on) => {
  let draft = 'fix it now please'
  let release = () => undefined as void
  const hold = [new Promise<void>(r => { release = r })]
  const w = hinting(on, { draft: () => draft, hold })
  await $.session.start(START)
  await draw($)
  await w.clock.advance(600)                                  // A's score starts and hangs
  draft = 'fix it now please, the login page'
  await draw($)
  await w.clock.advance(600)                                  // B is due while A still runs
  release()
  await settle()
  await w.clock.advance(600)
  expect(w.scored).toEqual(['fix it now please', 'fix it now please, the login page'])
  await draw($)
  expect(w.tails.at(-1)).toBe('· ▰▱▱▱▱  name a file, function, error or number')
})

// the outcome loop: an interrupted turn, and a follow-up, reported to pane.py --outcome with the texts on stdin
function outcomes(w: { ran: string[][]; stdins: (string | undefined)[] }) {
  return w.ran.flatMap((a, n) => (a.includes('--outcome') ? [`${a[a.indexOf('--outcome') + 1]} ${w.stdins[n]}`] : []))
}

const ABORT = (turnId: string, more = {}) => ({ answer: '', durationMs: 5, isAborted: true, turnId, reason: 'aborted', ...more }) as never

test('a turn you interrupt is reported with its prompt; a subagent ending is not', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'fix it now please' })
  await $.turn.start({ text: 'fix it now please', turnId: 't1' } as never)
  await $.turn.complete(ABORT('t1', { agentId: 'a1' }))
  await settle()
  expect(outcomes(w)).toEqual([])
  await $.turn.complete(ABORT('t1'))
  await settle()
  expect(outcomes(w)).toEqual(['aborted fix it now please'])
})

test('an interrupted turn you did not start blames nothing, and a queued prompt is not blamed for the running one', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'fix it now please' })
  await $.turn.start({ text: 'fix it now please', turnId: 't1' } as never)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' } as never)
  await $.turn.start({ text: '', turnId: 't2' } as never)                    // a scheduled task, a notification, /compact
  await $.turn.complete(ABORT('t2'))
  await $.prompt.submit({ text: 'make the header sticky on scroll' })
  await $.turn.start({ text: 'make the header sticky on scroll', turnId: 't3' } as never)
  await $.prompt.submit({ text: 'then add a footer with links' })            // queued while t3 runs
  await $.turn.complete(ABORT('t3'))
  await settle()
  expect(outcomes(w).filter(o => o.startsWith('aborted'))).toEqual(['aborted make the header sticky on scroll'])
})

test('a reply to a question Claude asked is not reported as a correction, nor a prompt from before /clear', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'update the parser for the new date format' })
  await $.turn.complete({ answer: 'Done. Should I also update the tests?', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' } as never)
  await $.prompt.submit({ text: 'no, just the parser' })
  await $.session.start(START)                                               // /clear: a new conversation
  await $.prompt.submit({ text: 'no, I meant the header' })
  await settle()
  expect(outcomes(w)).toEqual([])
})

test('each prompt you send reports the one before it, for a correction to be found', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'make it look nicer please' })
  await $.prompt.submit({ text: 'no, I meant the header' })
  await settle()
  expect(outcomes(w)).toEqual([`next ${JSON.stringify({ prev: 'make it look nicer please', text: 'no, I meant the header', project: '/w' })}`])
})

// hold (opt-in): a clearly vague prompt stops at Enter, goes back in the box; a second Enter sends it
async function scoredDraft($: Parameters<TestBody>[0], w: { clock: { advance: (ms: number) => Promise<void> } }) {
  await $.session.start(START)
  await draw($)
  await w.clock.advance(600)
}

test('hold stops a vague prompt at Enter with what it lacks, puts it back, and the second Enter sends it', async ($, on) => {
  const w = hinting(on, { holding: true })
  await scoredDraft($, w)
  const first = await $.prompt.submit({ text: 'fix it now please' })
  expect(first.drop).toBe('coachline held this: name a file, function, error or number. Press Enter again to send it as is')
  expect(w.filled).toEqual(['fix it now please'])
  expect(w.sent).toEqual([])
  const second = await $.prompt.submit({ text: 'fix it now please' })
  expect(second.drop).toBeUndefined()
  expect(w.sent).toEqual(['fix it now please'])
})

// Claude Code hands a dropped prompt back to the box as well, joined to what hold had already put there
const handBack = ($: Parameters<TestBody>[0], text: string) =>
  ($.prompt as unknown as { change: (e: object) => Promise<unknown> }).change({ text, cursor: text.length, origin: { kind: 'engine' } })

test('hold puts the prompt back once where Claude Code hands it back too, and the second Enter sends it', async ($, on) => {
  const w = hinting(on, { holding: true })
  await scoredDraft($, w)
  expect((await $.prompt.submit({ text: 'fix it now please' })).drop).toContain('coachline held this')
  await handBack($, 'fix it now please\nfix it now please')
  expect(w.filled).toEqual(['fix it now please', 'fix it now please'])
  expect((await $.prompt.submit({ text: 'fix it now please' })).drop).toBeUndefined()
  expect(w.sent).toEqual(['fix it now please'])
})

test('hold leaves the box alone once it holds something else', async ($, on) => {
  const w = hinting(on, { holding: true })
  await scoredDraft($, w)
  await $.prompt.submit({ text: 'fix it now please' })
  await handBack($, 'fix it now please in src/auth/login.js')
  await handBack($, 'fix it now please\nfix it now please')
  expect(w.filled).toEqual(['fix it now please'])
})

test('hold lets a prompt through when it is off', async ($, on) => {
  const off = hinting(on, { holding: false })
  await scoredDraft($, off)
  expect((await $.prompt.submit({ text: 'fix it now please' })).drop).toBeUndefined()
  expect(off.filled).toEqual([])
})

test('hold lets through a text not scored yet, and a prompt with a pasted image', async ($, on) => {
  const w = hinting(on, { holding: true })
  await scoredDraft($, w)
  expect((await $.prompt.submit({ text: 'something typed too fast to score' })).drop).toBeUndefined()
  const pasted = await $.prompt.submit({ text: 'fix it now please', attachments: [{ id: 'i1', kind: 'image' }] } as never)
  expect(pasted.drop).toBeUndefined()
  expect(w.filled).toEqual([])
})

test('hold never drops a prompt it cannot put back', async ($, on) => {
  const w = hinting(on, { holding: true, refuse: true })
  await scoredDraft($, w)
  expect((await $.prompt.submit({ text: 'fix it now please' })).drop).toBeUndefined()
  expect(w.sent).toEqual(['fix it now please'])
})

// the library: a turn that ended normally after your prompt becomes a candidate; a similar draft is told so, never filled
test('a turn that ends normally after your prompt is offered to the library with its project', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'add pagination to the orders table' })
  await $.turn.start({ text: 'add pagination to the orders table', turnId: 't1' } as never)
  await $.turn.complete({ answer: 'Done.', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' } as never)
  await $.turn.start({ text: '', turnId: 't2' } as never)
  await $.turn.complete({ answer: 'Done.', durationMs: 5, isAborted: false, turnId: 't2', reason: 'answer' } as never)
  await $.prompt.submit({ text: 'then sort it by date' })
  await $.turn.start({ text: 'then sort it by date', turnId: 't3' } as never)
  await $.turn.complete(ABORT('t3'))
  await settle()
  expect(outcomes(w).filter(o => o.startsWith('done'))).toEqual([`done ${JSON.stringify({ text: 'add pagination to the orders table', project: '/w' })}`])
})

test('a draft like a saved prompt says so under the box, and nothing is filled', async ($, on) => {
  const w = hinting(on, { score: () => ({ meter: '▰▰▰▰▱', hint: null, words: 14, hold: false, match: { id: 'abc', text: 'add pagination…' } }) })
  await scoredDraft($, w)
  await draw($)
  expect(w.tails.at(-1)).toBe('· ▰▰▰▰▱  ↻ similar prompt worked before')
  expect(w.filled).toEqual([])
})

// the Library view: saved prompts for this project, each with Use and Forget
const SAVED = { id: 'abc123abc123', text: 'add pagination to the orders table with 25 rows per page and keep the current sort order', uses: 2 }

test('the Library lists saved prompts; Use fills one and counts it, Forget removes it', async ($, on) => {
  const w = world(on, { out: STATE({ entries: [ASKING], library: [SAVED] }) })
  await $.session.start(START)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'library' })
  expect(await ui.find({ type: 'Text', text: /add pagination to the orders table/ })).toBeDefined()
  w.ran.length = 0
  await ui.press({ key: `libuse:${SAVED.id}` })
  await settle()
  expect(w.fills.map(f => f.text)).toEqual([SAVED.text])
  expect(w.ran.filter(a => a.includes('--library')).map(a => a.slice(2).join(' '))).toEqual([`--library used ${SAVED.id}`])
  w.ran.length = 0
  await ui.press({ key: `libforget:${SAVED.id}` })
  await settle()
  expect(w.ran.filter(a => a.includes('--library')).map(a => a.slice(2).join(' '))).toEqual([`--library forget ${SAVED.id}`])
  await ui.unmount()
})

test('an empty Library says what will land there', async ($, on) => {
  world(on, { out: STATE({ entries: [ASKING], library: [] }) })
  await $.session.start(START)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'library' })
  expect(await ui.find({ type: 'Text', text: /Prompts that worked first time land here: none yet in this project/ })).toBeDefined()
  await ui.unmount()
})

test('the pane asks for the library of this project', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  expect(w.ran.some(a => a.includes('--json') && a.includes('--project') && a.includes('/w'))).toBe(true)
})

test('the Library view has no Analyse button', async ($, on) => {
  world(on, { out: STATE({ entries: [{ ...CARD, after: '', state: 'local' }], library: [] }) })
  await $.session.start(START)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect(await ui.find({ type: 'Button', key: 'analyse' })).toBeDefined()
  await ui.press({ key: 'library' })
  expect(await ui.find({ type: 'Button', key: 'analyse' })).toBeUndefined()
  await ui.unmount()
})

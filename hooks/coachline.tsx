import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { PaneEntry, PaneLine, PaneState } from '../types'

const PANE = 'coachline'
const NO_PYTHON = 'coachline needs Python 3.9+ · run /coach doctor'
const NO_CLIPBOARD = 'no clipboard here: select the text instead'

const state = atom({ plugin: 'coachline', key: 'state' } as const, null as PaneState | null)
const error = atom({ plugin: 'coachline', key: 'error' } as const, '')
const sel = atom({ plugin: 'coachline', key: 'sel' } as const, -1)
const full = atom({ plugin: 'coachline', key: 'full' } as const, false)
const showPatterns = atom({ plugin: 'coachline', key: 'showPatterns' } as const, false)
const showLibrary = atom({ plugin: 'coachline', key: 'showLibrary' } as const, false)
const closed = atom({ plugin: 'coachline', key: 'closed' } as const, false)
const msg = atom({ plugin: 'coachline', key: 'msg' } as const, '')
// the hint under the prompt box: the draft it was worked out for, and the tail to draw while the box still holds that draft
const hint = atom({ plugin: 'coachline', key: 'hint' } as const,
  null as { draft: string; tail: string | null; hint: string | null; hold: boolean } | null)

const DEBOUNCE_MS = 600   // a pause in typing, not every key: one pane.py --score per pause
const HOLD_REARM_MS = 30000   // hold: the same prompt sent again within this goes through
let held = { text: '', at: -Infinity }
const ARM_MS = 5000       // Use over a draft: the second press within this replaces it
const ASK = /\[ASK:[^\]]*\]/g
let armedAt = -Infinity

// the brand accent (watch.py's TRUECOLOR): the terminal pane's name only; the desktop app and the editors keep their own theme
const ACCENT = '#E8735A'
// watch.py's colours (see CODE in scripts/watch.py): text by line kind, and each section's box and title by section
const COLOR: Record<string, string> = {
  prompt: 'whiteBright', blue: 'blueBright', bluedim: 'blueBright', enh: 'cyanBright', task: 'blueBright', meta: 'gray',
  better: 'magentaBright', src: 'gray',
}
const SECTION_COLOR: Record<string, string> = {
  prompt: 'whiteBright', improve: 'blueBright', enh: 'cyanBright', web: 'magentaBright', info: 'gray', bad: 'redBright',
}
// The desktop app and the editors (VS Code and its forks: Cursor, Windsurf, Antigravity, ...) draw in their own design systems,
// where a theme key follows their light and dark themes and an ANSI name is a fixed colour on the desktop (whiteBright is white
// on its light theme). There each section is the app's own card (a neutral rounded border), its small title in one accent, the
// text in the app's text colour, the quiet rows in its secondary text. The editors know no `skill` key: their terminal magenta.
const APP_SECTION: Record<string, Record<string, string>> = {
  desktop: { prompt: 'text', improve: 'suggestion', enh: 'claude', web: 'skill', info: 'inactive', bad: 'error' },
  vscode: { prompt: 'text', improve: 'suggestion', enh: 'claude', web: 'magenta', info: 'inactive', bad: 'error' },
}
// the surfaces that draw panes in a session they attach to after it started
const APPS = ['desktop', 'vscode']
const QUIET = new Set(['bluedim', 'meta', 'src'])

// discover.item_lines: "1. better: Name (kind) · you use this - why"
const FIND = /^(\d+\. )better: (.+?) \(([a-z]+)\)( · you use this)? - (.*)$/s

type Section = { section: string; head: PaneLine | null; rows: PaneLine[] }

// watch.py's boxed(): a section's title opens its box, and a blank line, a new title or another section closes it
function sections(lines: PaneLine[]): Section[] {
  const out: Section[] = []
  let cur: Section | null = null
  for (const l of lines) {
    const [section, kind] = l
    if (cur && (kind === 'blank' || section !== cur.section || kind === 'head')) cur = null
    if (kind === 'blank') continue
    if (!cur) {
      cur = { section, head: kind === 'head' ? l : null, rows: [] }
      out.push(cur)
      if (kind === 'head') continue
    }
    cur.rows.push(l)
  }
  return out
}

// Background work can outlive the module (a reload, the session ending): nothing is left to report to then.
const ignore = () => undefined

type Run = { ok: true; out: string } | { ok: false; err: string }

let active = false          // an interactive terminal session on macOS / Linux, or one the desktop app or an editor attached to; false
                            // under `claude -p`, the SDK and in the Windows terminal, which has watch.py's panel instead
let py: string[] | null = null
let pyChecked = false         // asked once: on a Mac without developer tools, each `python3` call can raise the install dialog
let inflight: Promise<PaneState | null> | null = null
let again = false
let width = 80
let poll: { cancel: () => void } | null = null
// after a prompt: the count of prompts that shows it, and until when to wait for it. An editor's session runs prompt.submit
// before the prompt is in its transcript, where pane.py reads it
let want = 0
let wantUntil = 0

// Windows often has neither python3 nor python, or has them as the Microsoft Store's stand-ins, which fail `--version`; the
// launcher python.org installs there is `py -3`
async function python($: EngineInterface): Promise<string[] | null> {
  if (pyChecked) return py
  pyChecked = true
  for (const cmd of [['python3'], ['python'], ['py', '-3']]) {
    try {
      const r = await $.process.run([...cmd, '--version'], { timeoutMs: 5000 })
      if (r.exitCode === 0) return (py = cmd)
    } catch {
      // not on PATH: try the next name
    }
  }
  return null
}

async function run($: EngineInterface, args: string[], stdin?: string): Promise<Run> {
  const p = await python($)
  if (!p) return { ok: false, err: NO_PYTHON }
  try {
    // a draft to score waits 3 s at most: a hung Python must not hold the hint for long
    const r = await $.process.run([...p, `${$.plugin.root}/scripts/pane.py`, ...args], stdin === undefined ? { timeoutMs: 20000 } : { timeoutMs: 3000, stdin })
    if (r.exitCode !== 0) {
      const last = r.stderr.trim().split('\n').pop() || `pane.py exited ${r.exitCode}`
      return { ok: false, err: `coachline: ${last} · run /coach doctor` }
    }
    return { ok: true, out: r.stdout }
  } catch (x) {
    return { ok: false, err: `coachline: ${String(x)} · run /coach doctor` }
  }
}

// One pane.py at a time: a refresh asked for while one runs is folded into a single rerun when it ends.
async function refresh($: EngineInterface): Promise<PaneState | null> {
  if (inflight) {
    again = true
    return inflight
  }
  inflight = (async () => {
    let s: PaneState | null = null
    do {
      again = false
      s = await refreshOnce($)
    } while (again)
    return s
  })()
  try {
    return await inflight
  } finally {
    inflight = null
  }
}

async function refreshOnce($: EngineInterface): Promise<PaneState | null> {
  // --width 0: unwrapped. The pane may sit beside the conversation, narrower than the viewport's columns, so its Text wraps each line
  const p = await folder($)
  const r = await run($, ['--json', '--session', await $.session.id(), '--width', '0', ...(p ? ['--project', p] : [])])
  let s: PaneState | null = null
  if (r.ok) {
    try {
      s = JSON.parse(r.out) as PaneState
    } catch {
      await update($, error, () => 'coachline: pane.py gave a bad answer · run /coach doctor')
      return null
    }
  } else {
    await update($, error, () => r.err)       // the last good state stays
    return null
  }
  await update($, error, () => '')
  await update($, state, () => s)
  // an analysis or this session's web research still to come: keep checking, since the turn may go on long after either lands
  const waiting = s.entries.length < want && (await $.clock.now()) < wantUntil
  const busy = s.entries.some(e => e.state === 'pending') || !!s.researching || waiting
  if (busy && !poll) poll = $.clock.every(3000, () => void refresh($).catch(ignore))
  if (!busy && poll) {
    poll.cancel()
    poll = null
  }
  return s
}

// Opens when the last answer says auto-open is on, or when there is no answer at all (no Python, pane.py failing): the pane then
// shows why, and the person can close it.
async function openIfWanted($: EngineInterface, s: PaneState | null): Promise<void> {
  if (s ? s.auto_open : (await read($, state)) === null) await open($)
}

async function startUp($: EngineInterface): Promise<void> {
  await openIfWanted($, await refresh($))
}

function wake($: EngineInterface): void {
  if (active) return
  active = true
  void startUp($).catch(ignore)              // the first prompt never waits for pane.py
}

async function open($: EngineInterface): Promise<void> {
  if (await read($, closed)) return
  const panes = await $.ui.panes()
  if (panes.some((p: { id: string; isPlaced: boolean }) => p.id === PANE && p.isPlaced)) return
  await $.ui.open({ id: PANE, title: 'coachline' })
}

// The draft goes to pane.py on stdin only (never argv, never a file, never Claude), after DEBOUNCE_MS without a change. One score
// runs at a time; an answer for a draft the box no longer holds is dropped.
let waiting: { cancel: () => void } | null = null
let planned = ''
let scoring = false

function schedule($: EngineInterface, draft: string) {
  if (draft === planned) return
  planned = draft
  waiting?.cancel(); waiting = null
  // the drawn line is reused until the hint changes: a tail for another draft must go now, not when the next score lands
  void update($, hint, h => (h && h.draft === draft ? h : null)).catch(ignore)
  if (!draft.trim()) return
  waiting = $.clock.after(DEBOUNCE_MS, () => {
    waiting = null
    void score($, draft).catch(ignore)
  })
}

// the session's folder: known from session.start, else (after a reload of this module) asked for
async function folder($: EngineInterface): Promise<string> {
  const now = await $.session.cwd().catch(() => '')      // asked each time: /cd or a worktree move changes it
  if (now) project = now
  return project
}

async function score($: EngineInterface, draft: string) {
  if (scoring) return                     // the running score picks up the newest draft when it ends
  scoring = true
  try {
    if ((await read($, state))?.hints === false) return
    const p = await folder($)
    const r = await run($, p ? ['--score', '--project', p] : ['--score'], draft)
    if (!r.ok) return
    const d = JSON.parse(r.out) as { meter: string | null; hint: string | null; words: number; hold?: boolean; match?: { id: string; text: string } | null }
    if ((await $.prompt.read()).text !== draft) return
    const tail = d.meter && d.words >= 3 ? `· ${d.meter}${d.hint ? `  ${d.hint}` : ''}${d.match ? '  ↻ similar prompt worked before' : ''}` : null
    await update($, hint, () => ({ draft, tail, hint: d.words >= 3 ? d.hint : null, hold: !!d.hold }))
  } finally {
    scoring = false
    if (planned !== draft && planned.trim() && !waiting) void score($, planned).catch(ignore)   // typed while this one ran
  }
}

// The outcome loop: the last prompt YOU sent (not a plugin's, a schedule's or a peer's), reported when you interrupt its turn, and
// with your next prompt so pane.py can tell a correction ("no, I meant…"). Texts go on stdin; pane.py keeps a redacted line, locally.
const HUMAN = ['composer', 'sdk', 'bridge']
let last: string | null = null
// the main loop's running turn, and its prompt only when it is the one you sent: a schedule's or /compact's turn blames nothing
let running: { turnId: string; text: string | null } | null = null
let project = ''      // the session's folder: the library's project, and where a similar saved prompt is looked for
let asked = false     // the last answer ended in a question: "no, just the parser" answers it, it corrects nothing

// Use: a text into the prompt box, its [ASK] gaps in bold; never sent (Q7). A draft in the box is replaced only on a second press
// within ARM_MS. Where the box does not take it, it is copied. Answers what to tell the person, and whether the text got anywhere.
async function fillBox($: EngineInterface, text: string, surface: string): Promise<{ note: string; done: boolean }> {
  const now = await $.clock.now()
  if ((await $.prompt.read()).text.trim() && now - armedAt > ARM_MS) {
    armedAt = now
    return { note: 'your prompt box has a draft: press Use again to replace it', done: false }
  }
  armedAt = -Infinity
  const decorations = [...text.matchAll(ASK)].map(m => ({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, bold: true }))
  const r = await $.prompt.fill({ text, mode: 'replace', decorations })
  if (r.isFilled) return { note: text.includes('[ASK:') ? 'in your prompt box: fill the [ASK] parts, then send' : 'in your prompt box: send it when ready', done: true }
  if (r.refusal === 'dialog') return { note: 'close the dialog first, then press Use', done: false }
  // no box here (the desktop app, an editor), or a cause unknown: the clipboard never touches the box, so copy
  const c = await $.ui.copy({ text, surface: surface as never })
  const why = r.refusal === 'no_composer' ? 'no prompt box here' : 'the prompt box did not take it'
  return c.isCopied ? { note: `copied instead: ${why}`, done: true } : { note: NO_CLIPBOARD, done: false }
}

export const register: Register = on => {
  // The terminal's pane, but not the Windows terminal's, which has watch.py's panel. The desktop app and the editors' Claude Code
  // extension run their session as an SDK host does (no surface, not interactive) and attach afterwards, after its first
  // prompt: session.attach; at a reload they are already attached
  on('session.start', async ($, e, next) => {
    last = null; running = null; asked = false; held = { text: '', at: -Infinity }     // a new conversation (/clear, a resume)
    project = e.cwd
    const r = await next(e)
    if ((e.isInteractive && (await $.env.get('OS')) !== 'Windows_NT') || (await $.session.surfaces()).some(x => APPS.includes(x))) wake($)
    return r
  })

  on('session.attach', async ($, e, next) => {
    const r = await next(e)
    if (APPS.includes(e.surface)) wake($)
    return r
  })

  on('prompt.submit', async ($, e, next) => {
    // hold (opt-in): only on the hint already worked out for exactly this text, so Enter never waits on Python; and only when the
    // text can go back in the box, so nothing is lost
    const h = await read($, hint)
    if (h?.hold && h.hint && h.draft === e.text && !e.command && !e.attachments?.length && (!e.origin || HUMAN.includes(e.origin.kind))) {
      const now = await $.clock.now()
      if (!(held.text === e.text && now - held.at < HOLD_REARM_MS) && (await $.prompt.fill({ text: e.text, mode: 'replace' })).isFilled) {
        held = { text: e.text, at: now }
        return { drop: `coachline held this: ${h.hint}. Press Enter again to send it as is` }
      }
    }
    const r = await next(e)
    if (r.drop === undefined && !e.command && (!e.origin || HUMAN.includes(e.origin.kind))) {
      const prev = last
      last = e.text
      if (prev && !asked) void run($, ['--outcome', 'next'], JSON.stringify({ prev, text: e.text, project })).catch(ignore)
      asked = false
    }
    if (!active) return r
    await update($, sel, () => -1)             // follow the newest prompt
    let s = await read($, state)
    if (!s && inflight) s = await inflight     // the session start's first answer, if it is still coming
    want = (s?.entries.length ?? 0) + 1
    wantUntil = (await $.clock.now()) + 60000
    await openIfWanted($, s)                   // from a prompt the person entered: placed at any width
    void refresh($).catch(ignore)
    return r
  })

  on('turn.start', async ($, e, next) => {
    const r = await next(e)
    if (!e.agentId) running = { turnId: e.turnId, text: e.text && e.text === last ? e.text : null }
    return r
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    if (!e.agentId) {
      const t = running?.turnId === e.turnId ? running.text : null
      if (e.isAborted && t) void run($, ['--outcome', 'aborted'], t).catch(ignore)
      if (!e.isAborted && t) void run($, ['--outcome', 'done'], JSON.stringify({ text: t, project })).catch(ignore)   // a library candidate
      asked = !e.isAborted && e.answer.trim().endsWith('?')
      running = null
    }
    if (active) await refresh($)
    return r
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && e.origin.kind === 'person') await update($, closed, () => true)
    return next(e)
  })

  on('prompt.edit', async ($, e, next) => {
    const box = await next(e)
    schedule($, box.text)
    return box
  })

  on('prompt.change', async ($, e, next) => {
    schedule($, e.text)
    return next(e)
  })

  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    if (!e.props.isDraft || e.props.isWorking) return next(e)
    const { text } = await $.prompt.read()
    schedule($, text)
    const h = await read($, hint)
    return h && h.draft === text && h.tail ? next({ ...e, props: { ...e.props, tail: h.tail } }) : next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    // the desktop app or an editor: their own design system. An editor spaces in cells, not the desktop's step names, and pads no
    // bordered Box by itself
    const app = APPS.includes(e.surface)
    const ed = e.surface === 'vscode'
    const sp = (step: 'xs' | 'sm', cells: number) => (ed ? cells : step)
    // an editor wraps a row Box by default: a bullet's dot would land on a line of its own
    const nw = ed ? 'nowrap' : undefined
    const accentOf = APP_SECTION[e.surface] ?? APP_SECTION.desktop!
    // an app's body is narrower than its viewport, which counts the conversation beside it
    width = (app ? e.props.bodyColumns : e.viewport?.columns) ?? width
    const s = await read($, state)
    const err = await read($, error)
    const note = await read($, msg)
    if (!s) return <Text dimColor>{err || 'coachline: loading…'}</Text>

    const count = `${s.entries.length} prompt${s.entries.length === 1 ? '' : 's'}`
    // an app names the pane in its own title bar: the row only says what it shows
    const header = app ? (
      <Box key="header" justifyContent="space-between" flexWrap={nw}>
        <Text size="footnote" dimColor>This thread · {count}</Text>
        <Text size="footnote" color={s.ai ? 'success' : 'inactive'}>{s.ai ? '● Claude on' : '○ Claude off'}</Text>
      </Box>
    ) : (
      <Box key="header">
        <Text bold color={ACCENT}>coachline</Text>
        <Text bold> · this thread · {count}</Text>
        <Text>{'  '}</Text>
        <Text color={s.ai ? 'green' : 'gray'}>{s.ai ? '● Claude on' : '○ Claude off'}</Text>
      </Box>
    )
    const footer = [
      err ? <Text key="err" color={app ? 'error' : 'red'}>{err}</Text> : null,
      note ? <Text key="msg" dimColor>{note}</Text> : null,
      s.notice && !s.entries.length ? <Text key="notice" dimColor>{s.notice}</Text> : null,
    ]
    if (!s.entries.length) {
      return (
        <Box flexDirection="column" gap={app ? sp('sm', 0.5) : 0}>
          {header}
          <Text dimColor>Send a prompt: coachline coaches it here.</Text>
          {footer}
        </Box>
      )
    }

    const at = await read($, sel)
    const i = at < 0 || at >= s.entries.length ? s.entries.length - 1 : at
    const cur: PaneEntry | undefined = s.entries[i]
    if (!cur) return <Text dimColor>coachline: loading…</Text>
    const isFull = await read($, full)
    const isLibrary = await read($, showLibrary)
    const saved = s.library ?? []
    const pats = await read($, showPatterns)

    const copy = async () => {
      const r = await $.ui.copy({ text: cur.after, surface: e.surface })
      await update($, msg, () => (r.isCopied ? `copied the enhanced prompt (${cur.after.length} characters)` : NO_CLIPBOARD))
    }
    // the enhanced prompt into the prompt box, its [ASK] gaps in bold; never sent: you fill the gaps and press Enter (Q7)
    const use = async () => {
      const r = await fillBox($, cur.after, e.surface)
      await update($, msg, () => r.note)
    }
    const useSaved = async (id: string, text: string) => {
      const r = await fillBox($, text, e.surface)
      await update($, msg, () => r.note)
      if (r.done) void run($, ['--library', 'used', id]).then(() => refresh($)).catch(ignore)
    }
    const forgetSaved = async (id: string) => {
      const r = await run($, ['--library', 'forget', id])
      await update($, msg, () => (r.ok ? 'forgotten: it will not be offered again' : r.err))
      await refresh($)
    }
    const analyse = async () => {
      const r = await run($, s.session ? ['--enhance', cur.key, '--session', s.session] : ['--enhance', cur.key])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
      await refresh($)
    }
    const mark = async (status: 'dismissed' | 'adopted', id: string) => {
      const r = await run($, ['--mark', status, id])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
      await refresh($)
    }
    const research = async () => {
      const r = await run($, s.session ? ['--research', cur.key, '--session', s.session] : ['--research', cur.key])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
    }
    const install = async () => {
      if (!s.skill) return
      const r = await run($, ['--install', s.skill])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
    }

    const line = (l: PaneLine, n: number) => {
      const [section, kind, text, , action] = l
      const accent = accentOf[section]
      if (kind === 'itemacts' && action?.startsWith('item:')) {
        const id = action.slice('item:'.length)
        return (
          <Box key={`l${n}`} paddingLeft={3} marginTop={app ? sp('xs', 0.25) : 0} flexWrap={nw}>
            <Button key={`hide:${id}`} label="Hide" onPress={() => mark('dismissed', id)} />
            {!app && <Text>{'  '}</Text>}
            <Button key={`use:${id}`} label="I use this" onPress={() => mark('adopted', id)} />
          </Box>
        )
      }
      if (action === 'enter') return <Button key="whole" label="Show the whole prompt" onPress={() => update($, full, () => true)} />
      const find = kind === 'better' ? FIND.exec(text) : null
      if (find) {
        const [, num, name, type, used, why] = find
        return (
          // a web find: its name and kind, then why, the source and the buttons beneath, each item apart from the one before
          <Box key={`l${n}`} marginTop={n % 1000 ? 1 : 0} alignItems={app ? 'flex-start' : undefined} flexWrap={nw}>
            <Text color={app ? accent : COLOR.better}>{num}</Text>
            <Box flexDirection="column">
              <Box flexWrap={nw}>
                {app ? <Text weight="semibold" bold>{name}</Text> : <Text bold color={COLOR.better}>{name}</Text>}
                <Text dimColor size={app ? 'footnote' : undefined}>{`  ${type}${used ?? ''}`}</Text>
              </Box>
              <Text>{why}</Text>
            </Box>
          </Box>
        )
      }
      if (kind === 'src') {
        return (
          <Box key={`l${n}`} paddingLeft={3} flexWrap={nw}>
            <Text dimColor size={app ? 'footnote' : undefined}>{text.trim()}</Text>
          </Box>
        )
      }
      const dot = /^[•-] /.exec(text)?.[0]
      if (app) {
        // the app's text; a bullet's dot in the section's accent, on its first line, its wrapped lines under its text
        if (dot) {
          return (
            <Box key={`l${n}`} alignItems="flex-start" flexWrap={nw}>
              <Text color={accent}>{dot}</Text>
              <Text dimColor={QUIET.has(kind)}>{text.slice(dot.length)}</Text>
            </Box>
          )
        }
        // an empty Text has no height in an app: a blank line of the enhanced prompt keeps its row
        return <Text key={`l${n}`} dimColor={QUIET.has(kind)} weight={kind === 'task' ? 'medium' : undefined}>{text || ' '}</Text>
      }
      if (dot) {
        return (
          // a bullet's wrapped lines start under its text, as watch.py's bullet() wraps them
          <Box key={`l${n}`}>
            <Text color={COLOR[kind]} dimColor={kind === 'bluedim'}>{dot}</Text>
            <Text color={COLOR[kind]} dimColor={kind === 'bluedim'}>{text.slice(dot.length)}</Text>
          </Box>
        )
      }
      return <Text key={`l${n}`} color={COLOR[kind]} dimColor={QUIET.has(kind)} bold={kind === 'prompt'}>{text}</Text>
    }

    // as on watch.py's panel: each section a rounded box in its colour. The title opens it (an element set on the border is not
    // drawn), its label or Copy button right after, never against the pane's right edge, where the pane's own close mark is.
    // In an app: its own card, which the desktop pads itself and an editor in cells; your prompt on the surface of your own
    // messages, its title row spread across the card, the close mark being in the app's title bar
    const box = (sec: Section, n: number, body: RenderChildren[]) => {
      const [, , title, right, action] = sec.head ?? []
      // in an app a note with no title (the first-run notice) is plain text, not a card
      if (!sec.section || (app && sec.section === 'info' && !title)) return <Box key={`s${n}`} flexDirection="column">{body}</Box>
      const copyButton = (
        <Box key="acts" gap={1} flexWrap={nw}>
          <Button key="use" label="Use" onPress={use} />
          <Button key="copy" label="Copy" variant={app ? 'primary' : undefined} onPress={copy} />
        </Box>
      )
      if (app) {
        const color = accentOf[sec.section] ?? 'inactive'
        return (
          <Box key={`s${n}`} flexDirection="column" borderStyle="round" gap={sp('xs', 0.25)}
            paddingX={ed ? 1 : undefined} paddingY={ed ? 0.5 : undefined}
            backgroundColor={sec.section === 'prompt' ? 'userMessageBackground' : undefined}>
            {title && (
              <Box justifyContent="space-between" alignItems="center" gap={sp('sm', 1)} flexWrap={nw}>
                <Text size="footnote" weight="semibold" bold color={color}>{title}</Text>
                {action === 'copy' ? copyButton : right ? <Text size="footnote" dimColor>{right}</Text> : null}
              </Box>
            )}
            {body}
          </Box>
        )
      }
      const color = SECTION_COLOR[sec.section] ?? 'gray'
      return (
        <Box key={`s${n}`} flexDirection="column" borderStyle="round" borderColor={color} paddingX={1}>
          {title && (
            <Box>
              <Text bold color={color}>{title}</Text>
              <Text>{'  '}</Text>
              {action === 'copy' ? copyButton : right ? <Text dimColor>{right}</Text> : null}
            </Box>
          )}
          {body}
        </Box>
      )
    }

    const library = [box({ section: 'enh', head: ['enh', 'head', 'Library', `${saved.length} saved in this project`, null], rows: [] }, 0,
      saved.length
        ? saved.flatMap(x => [
            <Text key={`lt${x.id}`} color={app ? undefined : COLOR.enh}>{x.text}</Text>,
            <Box key={`lb${x.id}`} gap={1} flexWrap={nw}>
              <Button key={`libuse:${x.id}`} label="Use" onPress={() => useSaved(x.id, x.text)} />
              <Button key={`libforget:${x.id}`} label="Forget" onPress={() => forgetSaved(x.id)} />
            </Box>,
          ])
        : [<Text key="libempty" dimColor>Prompts that worked first time land here: none yet in this project.</Text>])]
    const card = isLibrary ? library : isFull
      ? [box({ section: 'prompt', head: ['prompt', 'head', 'Your prompt', '', null], rows: [] }, 0, [
          <Text key="fulltext" color={app ? undefined : 'whiteBright'}>{cur.text}</Text>,
          <Button key="less" label="Show less" onPress={() => update($, full, () => false)} />,
        ])]
      : sections(cur.lines).map((sec, n) => box(sec, n, sec.rows.map((l, k) => line(l, n * 1000 + k))))
    // watch.py's card names keys ("press e"); here one Analyse button stands for them, whatever the prompt's state
    const canAnalyse = !cur.after && cur.state !== 'off' && !isLibrary

    return (
      <Box flexDirection="column" gap={app ? sp('sm', 0.5) : 0}>
        {header}
        <Box flexDirection="column" marginY={app ? 0 : 1} gap={app ? sp('sm', 0.5) : 1}>{card}</Box>
        {canAnalyse && <Button key="analyse" label={cur.state === 'pending' ? 'Analyse again' : 'Analyse'}
          variant={app ? 'primary' : undefined} onPress={analyse} />}
        {s.research && !!cur.after && cur.state !== 'off' && !isLibrary && <Button key="research" label="Look again on the web" onPress={research} />}
        <Button key="library" label={isLibrary ? 'Back to the prompt' : `Library (${saved.length})`} onPress={() => update($, showLibrary, v => !v)} />
        {s.patterns.length > 0 && (
          <Box flexDirection="column" gap={app ? sp('xs', 0.25) : 0}>
            <Button key="patterns" label={pats ? 'Hide patterns' : `${s.patterns.length} pattern${s.patterns.length === 1 ? '' : 's'} from your past chats`}
              onPress={() => update($, showPatterns, v => !v)} />
            {pats && s.patterns.map((p, n) => <Text key={`p${n}`} color={app ? undefined : 'blueBright'}>{p}</Text>)}
            {s.skill && <Button key="skill" label={`Install the drafted skill /${s.skill}`} onPress={install} />}
          </Box>
        )}
        <Box flexDirection="column" gap={app ? sp('xs', 0.25) : 0}>
          {app ? <Text size="footnote" weight="semibold" dimColor>Prompts in this thread</Text> : <Text dimColor>Prompts in this thread</Text>}
          {s.entries.map((x, n) => (
            <Button key={`e${n}`} label={`${n === i ? '›' : ' '} ${x.glyph} ${x.stamp}  ${x.text.replace(/\s+/g, ' ').slice(0, Math.max(10, width - (app ? 0 : 16)))}`}
              dimColor={app && n !== i ? true : undefined} onPress={() => update($, sel, () => n)} />
          ))}
        </Box>
        {footer}
      </Box>
    )
  })
}

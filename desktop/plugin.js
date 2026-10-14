import { host, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

function Workspace({ ctx }) {
  const profile = useValue(host.state.profile)
  const session = useValue(host.state.activeSessionId)
  const gateway = useValue(host.state.gateway)
  const epoch = useRef(0)
  const heading = useRef(null)
  const [view, setView] = useState(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [busy, setBusy] = useState(false)
  const load = async (path, opts) => {
    const current = ++epoch.current
    setBusy(true)
    setError('')
    try {
      const result = await ctx.rest(path, opts)
      if (current === epoch.current) {
        setView(result)
        heading.current?.focus()
      }
    } catch {
      if (current === epoch.current) {
        setView(null)
        setError('Minefield backend unavailable. Enable the matching agent plugin in this profile.')
      }
    } finally {
      if (current === epoch.current) setBusy(false)
    }
  }
  useEffect(() => {
    ++epoch.current
    setView(null)
    setSelected([])
    load('/workspace')
    return () => { ++epoch.current }
  }, [profile, session, gateway])
  const button = (label, action, disabled = busy) => jsx('button', {
    type: 'button', disabled, onClick: action,
    className: 'rounded border px-3 py-2 disabled:opacity-50', children: label
  }, label)
  return jsxs('section', {
    className: 'flex h-full min-w-0 flex-col gap-3 overflow-auto p-3 text-sm',
    style: { color: 'var(--ui-text-primary)', background: 'var(--ui-background)' },
    'aria-label': 'Minefield diagnostic workspace',
    children: [
      jsx('h2', { tabIndex: -1, ref: heading, children: 'Minefield' }),
      jsx('p', { children: 'Local preview · Sharing OFF · Live diagnostics ON HOLD' }),
      jsx('p', { role: 'status', 'aria-live': 'polite', children: busy ? 'Loading local view…' : error || 'No diagnostic requests run.' }),
      jsxs('nav', { 'aria-label': 'Minefield views', className: 'flex flex-wrap gap-2', children: [
        button('Home', () => { setSelected([]); load('/workspace') }),
        button('Choose checks', () => load('/checks')),
        button('Privacy', () => load('/privacy')),
        button('Cancel / back', () => { ++epoch.current; setSelected([]); load('/workspace') }, false)
      ] }),
      view?.checks ? jsxs('fieldset', { children: [
        jsx('legend', { children: 'Select named checks — preview only' }),
        ...view.checks.map(check => jsxs('label', { className: 'flex items-start gap-2 py-2', children: [
          jsx('input', { type: 'checkbox', checked: selected.includes(check.id),
            onChange: event => setSelected(old => event.target.checked ? [...old, check.id] : old.filter(id => id !== check.id)) }),
          jsx('span', { children: `${check.title} (${check.id}) · ≤${check.request_cost} generation requests` })
        ] }, check.id)),
        button('Review selection', () => load('/preview', { method: 'POST', body: { probe_ids: selected } }), busy || !selected.length)
      ] }) : null,
      view ? jsx('pre', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }, children: JSON.stringify(view, null, 2) }) : null,
      jsx('p', { role: 'note', children: 'Execution unavailable on this surface.' }),
      jsx('p', { children: 'A trusted host approval bridge and exact request review are still required. No live target or production recipient is configured.' })
    ]
  })
}

export default {
  id: 'hermes-minefield',
  name: 'Minefield',
  register(ctx) {
    ctx.register({ id: 'workspace', area: 'panes', title: 'Minefield',
      data: { placement: 'right', width: '420px' }, render: () => jsx(Workspace, { ctx }) })
  }
}

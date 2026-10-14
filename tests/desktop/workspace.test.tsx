import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { $activeSessionId } from '../../../host/apps/desktop/src/store/session'
import { createPluginContext } from '../../../host/apps/desktop/src/contrib/plugin'
import { registry } from '../../../host/apps/desktop/src/contrib/registry'
import plugin from '../../desktop/plugin.js'

const disposers: Array<() => void> = []
afterEach(() => { cleanup(); disposers.splice(0).reverse().forEach(fn => fn()) })

it('registers through real SDK context, operates preview controls, and disposes', async () => {
  const ctx = createPluginContext(plugin.id, fn => disposers.push(fn))
  // Backend boundary fixture only: SDK and registry are real selected-host source.
  ctx.rest = vi.fn(async (path, options) => {
    if (path === '/checks') return { checks: [{ id: 'request_validation', title: 'Validation', request_cost: 2 }] }
    if (path === '/preview') return { reviewed: options.body.probe_ids, approval: false }
    return { view: path, sharing: 'OFF' }
  }) as any
  plugin.register(ctx)
  const pane = registry.getArea('panes').find(p => p.id === 'hermes-minefield:workspace')!
  expect(pane.source).toBe('plugin:hermes-minefield')
  render(pane.render!({} as any) as any)
  await screen.findByText(/"view": "\/workspace"/)
  fireEvent.click(screen.getByRole('button', { name: 'Choose checks' }))
  await screen.findByRole('checkbox')
  expect(screen.getByRole('button', { name: 'Review selection' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Review selection' }))
  await screen.findByText(/"reviewed"/)
  expect(ctx.rest).toHaveBeenLastCalledWith('/preview', { method: 'POST', body: { probe_ids: ['request_validation'] } })
  fireEvent.click(screen.getByRole('button', { name: 'Privacy' }))
  await screen.findByText(/"view": "\/privacy"/)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel \/ back' }))
  await screen.findByText(/"view": "\/workspace"/)
  fireEvent.click(screen.getByRole('button', { name: 'Home' }))
  await waitFor(() => expect(document.activeElement?.textContent).toBe('Minefield'))
  expect(screen.queryByRole('button', { name: /Approve/ })).toBeNull()
  cleanup()
  disposers.splice(0).reverse().forEach(fn => fn())
  expect(registry.getArea('panes').find(p => p.id === 'hermes-minefield:workspace')).toBeUndefined()
})

it('discards an old session response and remains usable when the backend fails', async () => {
  const ctx = createPluginContext(plugin.id, fn => disposers.push(fn))
  let resolveOld: (value: unknown) => void = () => { throw new Error('not requested') }
  let first = true
  ctx.rest = vi.fn(async () => {
    if (first) {
      first = false
      return new Promise(resolve => { resolveOld = resolve })
    }
    return { view: 'new-session' }
  }) as any
  plugin.register(ctx)
  const pane = registry.getArea('panes').find(p => p.id === 'hermes-minefield:workspace')!
  render(pane.render!({} as any) as any)
  await act(async () => { $activeSessionId.set('synthetic-new-session') })
  await screen.findByText(/new-session/)
  await act(async () => { resolveOld({ view: 'OLD_PRIVATE_CANARY' }) })
  expect(screen.queryByText(/OLD_PRIVATE_CANARY/)).toBeNull()
  ctx.rest = vi.fn(async () => { throw new Error('private backend detail') }) as any
  fireEvent.click(screen.getByRole('button', { name: 'Privacy' }))
  await screen.findByText(/Minefield backend unavailable/)
  expect(screen.queryByText(/private backend detail/)).toBeNull()
  expect(screen.getByRole('button', { name: 'Home' }).disabled).toBe(false)
  cleanup()
  $activeSessionId.set(null)
})

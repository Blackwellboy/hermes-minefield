import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const app = path.resolve(here, '../../../host/apps/desktop').replaceAll('\\', '/')
const require = createRequire(path.join(app, 'package.json'))
const dependency = (name: string) => path.dirname(require.resolve(name + '/package.json'))
export default {
  root: app,
  resolve: { alias: {
    '@hermes/plugin-sdk': path.join(app, 'src/sdk/index.ts'),
    '@hermes/shared/billing': path.resolve(app, '../shared/src/billing-types.ts'),
    '@hermes/shared/color': path.resolve(app, '../shared/src/color.ts'),
    '@hermes/shared': path.resolve(app, '../shared/src'),
    '@': path.join(app, 'src'),
    'react': dependency('react'),
    'react-dom': dependency('react-dom'),
    '@testing-library/react': dependency('@testing-library/react'),
    'vitest': path.resolve(app, '../../node_modules/vitest/dist/index.js'),
  } },
  test: {
    environment: 'jsdom', globals: true,
    setupFiles: ['./vitest.setup.ts', '../../../adapter/tests/desktop/network-fence.ts'],
    include: ['../../../adapter/tests/desktop/*.test.tsx'],
    testTimeout: 15000, hookTimeout: 30000,
    env: { NODE_ENV: 'development' },
  },
}

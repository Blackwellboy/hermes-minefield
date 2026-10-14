// Deny renderer networking before importing the actual SDK graph.
globalThis.fetch = async () => { throw new Error('TEST_NETWORK_DENIED') }
globalThis.WebSocket = class { constructor() { throw new Error('TEST_NETWORK_DENIED') } } as any
globalThis.XMLHttpRequest = class { constructor() { throw new Error('TEST_NETWORK_DENIED') } } as any

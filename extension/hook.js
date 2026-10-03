// Runs in the page context. Observes incoming data only. Never sends to Yahoo.
(() => {
  // Only Yahoo Fantasy data. Ads and tracking calls are ignored.
  const WANTED = /fantasysports\.yahoo\.com|\/tdfan\//
  const emit = (kind, data) => {
    try {
      window.postMessage({ __fantasyCapture: true, kind, url: location.href, ts: Date.now(), data }, '*')
    } catch (_) {}
  }

  // WebSocket: record incoming messages and the socket URL.
  const NativeWS = window.WebSocket
  window.WebSocket = function (url, protocols) {
    const ws = protocols === undefined ? new NativeWS(url) : new NativeWS(url, protocols)
    emit('ws_open', { url: String(url) })
    ws.addEventListener('message', (e) => {
      if (typeof e.data === 'string') emit('ws_message', { url: String(url), body: e.data })
      else emit('ws_message', { url: String(url), binary: true })
    })
    return ws
  }
  window.WebSocket.prototype = NativeWS.prototype
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 })

  // fetch: record JSON/text responses.
  const nativeFetch = window.fetch
  window.fetch = async function (...args) {
    const res = await nativeFetch.apply(this, args)
    try {
      const url = String(args[0] instanceof Request ? args[0].url : args[0])
      const type = res.headers.get('content-type') || ''
      if (WANTED.test(url) && /json|text/.test(type)) {
        res.clone().text().then((body) => emit('fetch', { url, status: res.status, type, body }))
      }
    } catch (_) {}
    return res
  }

  // XHR: record responses.
  const open = XMLHttpRequest.prototype.open
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__captureUrl = String(url)
    this.addEventListener('load', () => {
      try {
        if (WANTED.test(this.__captureUrl) && (this.responseType === '' || this.responseType === 'text')) {
          emit('xhr', { url: this.__captureUrl, status: this.status, body: this.responseText })
        }
      } catch (_) {}
    })
    return open.call(this, method, url, ...rest)
  }
})()

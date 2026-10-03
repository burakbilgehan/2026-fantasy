// Isolated world. Forwards page events to the service worker, plus a rare DOM snapshot.
window.addEventListener('message', (e) => {
  if (e.source === window && e.data && e.data.__fantasyCapture) {
    const { kind, url, ts, data } = e.data
    chrome.runtime.sendMessage({ kind, url, ts, data })
  }
})

// One DOM snapshot after load, then every 5 minutes (debug only).
const snapshot = () => {
    chrome.runtime.sendMessage({
      kind: 'dom_snapshot',
      url: location.href,
      ts: Date.now(),
      data: { html: document.documentElement.outerHTML.slice(0, 2000000) },
    })
}
setTimeout(snapshot, 15000)
setInterval(snapshot, 300000)

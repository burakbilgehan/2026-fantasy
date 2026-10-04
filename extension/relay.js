// Isolated world. Forwards page events to the service worker.
window.addEventListener('message', (e) => {
  if (e.source === window && e.data && e.data.__fantasyCapture) {
    const { kind, url, ts, data } = e.data
    chrome.runtime.sendMessage({ kind, url, ts, data })
  }
})

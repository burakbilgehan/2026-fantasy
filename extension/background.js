// Posts captured events to the local backend only.
chrome.runtime.onMessage.addListener((event) => {
  fetch('http://localhost:8000/api/capture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(event),
  }).catch(() => {})
})

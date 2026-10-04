// Reads the transcript of the open YouTube watch page and POSTs it to the local
// receiver. Served by transcript_receiver.py at /grab.js?id=VIDEO_ID (__ID__ is
// replaced). Evaluated through a Trusted Types policy, so it is one expression.
//
// Two sources, first one wins:
// 1. Network: the panel's youtubei response (get_panel / get_transcript), hooked
//    before the click. Works in a hidden tab (the modern panel does not render
//    its rows while the tab is hidden, seen 2026-10-04).
// 2. DOM: transcript-segment-view-model (modern) or ytd-transcript-segment-renderer (old).
(async () => {
  const id = '__ID__';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const cap = [];
  if (!window.__grabHooked) {
    window.__grabHooked = true;
    window.__grabCap = cap;
    const of = window.fetch;
    window.fetch = async function (...a) {
      const r = await of.apply(this, a);
      try {
        const u = (a[0] && a[0].url) || String(a[0]);
        if (/youtubei\/v1\/(get_panel|get_transcript)/.test(u)) r.clone().text().then(t => window.__grabCap.push(t));
      } catch (e) {}
      return r;
    };
    const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return oo.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function () {
      this.addEventListener('load', () => {
        try { if (/youtubei\/v1\/(get_panel|get_transcript)/.test(String(this.__u))) window.__grabCap.push(this.responseText); } catch (e) {}
      });
      return os.apply(this, arguments);
    };
  }
  const fromNetwork = () => {
    for (const t of window.__grabCap || []) {
      let j; try { j = JSON.parse(t); } catch (e) { continue; }
      const segs = [];
      (function walk(o) {
        if (!o || typeof o !== 'object') return;
        if (o.transcriptSegmentViewModel) {
          const v = o.transcriptSegmentViewModel;
          segs.push({ts: v.timestamp, text: v.simpleText || v.text?.content || ''});
          return;
        }
        if (o.transcriptSegmentRenderer) {
          const v = o.transcriptSegmentRenderer;
          const ms = +v.startMs;
          segs.push({ts: `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`,
                     text: (v.snippet?.runs || []).map(x => x.text).join('') || v.snippet?.simpleText || ''});
          return;
        }
        for (const v of Object.values(o)) walk(v);
      })(j);
      if (segs.length) return segs;
    }
    return null;
  };
  const segEls = () => [...document.querySelectorAll('transcript-segment-view-model, ytd-transcript-segment-renderer')];
  const fromDom = () => segEls().map(s => {
    if (s.tagName.toLowerCase() === 'ytd-transcript-segment-renderer')
      return {ts: s.querySelector('.segment-timestamp')?.textContent.trim(), text: s.querySelector('.segment-text')?.textContent.trim()};
    const l = s.innerText.split('\n').map(x => x.trim()).filter(Boolean);
    return {ts: l[0], text: l.slice(2).join(' ')};
  });
  let out;
  try {
    for (let i = 0; i < 20 && document.querySelector('#movie_player')?.getPlayerResponse?.()?.videoDetails?.videoId !== id; i++) await sleep(500);
    const v = document.querySelector('video');
    if (v) { v.muted = true; v.pause(); }
    await sleep(1000);
    document.querySelector('#description-inline-expander #expand')?.click();
    await sleep(500);
    const open = () => {
      document.querySelector('#description-inline-expander #expand')?.click();
      const btns = [...document.querySelectorAll('ytd-video-description-transcript-section-renderer button')];
      (btns.find(b => b.offsetParent) || btns[0])?.click();
    };
    open();
    let segs = null, last = -1, stable = 0, how = '';
    for (let i = 0; i < 70 && !segs; i++) {
      await sleep(500);
      // No panel request yet (button not rendered at first click): click again.
      if ((i === 12 || i === 30) && !(window.__grabCap || []).length && !segEls().length) open();
      const net = fromNetwork();
      if (net) { segs = net; how = 'net'; break; }
      const c = segEls().length;
      if (c > 0) { if (c === last) { if (++stable >= 3) { segs = fromDom(); how = 'dom'; } } else { stable = 0; last = c; } }
    }
    if (!segs) throw new Error('no transcript');
    const pr = document.querySelector('#movie_player').getPlayerResponse();
    if (pr.videoDetails.videoId !== id) throw new Error('wrong video');
    const r = await fetch('http://127.0.0.1:8765/transcript', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({video_id: id, title: pr.videoDetails.title, channel: pr.videoDetails.author,
        publish_date: pr.microformat?.playerMicroformatRenderer?.publishDate || '',
        duration: +pr.videoDetails.lengthSeconds, segments: segs}),
    });
    out = `${id} ${r.status} ${segs.length} ${how}`;
  } catch (e) { out = `${id} FAIL ${e}`; }
  return out;
})()

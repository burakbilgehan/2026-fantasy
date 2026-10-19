// Yahoo league calendar and H2H matchups capture (season sim). The Yahoo Fantasy API is not approved
// for our app (cli `check`, 2026-10-18), so this reads the league web pages. Run in a logged-in Yahoo
// tab (Claude in Chrome, javascript tool) on any https://basketball.fantasysports.yahoo.com/nba/{league}/ page.
// Fixed procedure, read only:
// 1. Weeks 1..21: the league page with `matchup_week={w}&module=matchups` lists that week's matchups as
//    links `matchup?week={w}&mid1={a}&mid2={b}` (team ids). Playoff weeks (19..21) have none before seeding.
// 2. The same weeks on the matchup page give the day headers ("Tue 10/20" ... "Sun 10/25"): first and last day.
// The result goes to window.__yahooSchedule; copy it to data/raw/yahoo/{league}_schedule.json.
window.__yahooSchedule = { state: 'running' };
(async () => {
  try {
    const league = location.pathname.match(/\/nba\/(\d+)/)[1];
    const weeks = [];
    for (let w = 1; w <= 21; w++) {
      const lp = await (await fetch(`/nba/${league}?matchup_week=${w}&module=matchups`, { credentials: 'include' })).text();
      const pairs = new Set();
      for (const m of lp.matchAll(/matchup\?week=(\d+)&(?:amp;)?mid1=(\d+)&(?:amp;)?mid2=(\d+)/g)) {
        if (+m[1] === w) pairs.add([+m[2], +m[3]].sort((a, b) => a - b).join('-'));
      }
      const mp = await (await fetch(`/nba/${league}/matchup?week=${w}&mid1=1`, { credentials: 'include' })).text();
      const days = [...new Set(mp.match(/(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2}\/\d{1,2}/g) || [])];
      weeks.push({ week: w, first: days[0] ?? null, last: days[days.length - 1] ?? null, days: days.length,
        matchups: [...pairs].map((p) => p.split('-').map(Number)) });
    }
    window.__yahooSchedule = { state: 'done', league, captured_at: new Date().toISOString(), weeks };
  } catch (e) {
    window.__yahooSchedule = { state: 'error', error: String(e) };
  }
})();

// Fantrax projection capture (T-025). Run in a logged-in Fantrax tab (Claude in Chrome,
// javascript tool), on any https://www.fantrax.com page. Fixed procedure, no judgment needed:
// 1. Find a public NBA league (getPublishedLeagues). Projections exist only on a league's
//    players page; every league shows the same projection set (verified 2026-10-05).
// 2. Read every page of getPlayerStats: view "Projected - Season" (the default), scoring
//    category type 1 = Standard (GP, MIN, FGM, FGA, FG%, FTM, FTA, FT%, 3PTM, REB, AST, ST,
//    BLK, TO, PTS, all per game), 250 rows per page.
// 3. POST the rows to the local backend (text/plain, no-cors). Chrome asks once for local
//    network access; the user allowed it on 2026-10-05.
// The script runs in the background and writes its state to window.__fantraxCapture; poll it.
// No password or cookie leaves the tab. Then run `make players-sync SOURCE=fantrax`.
window.__fantraxCapture = { state: 'running', rows: 0 };
(async () => {
  try {
    const body = (msgs) => JSON.stringify({ msgs, uiv: 3, refUrl: location.href, dt: 0, at: 0, tz: 'UTC' });
    const req = async (msgs, leagueId) => (await fetch('/fxpa/req' + (leagueId ? '?leagueId=' + leagueId : ''), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body(msgs),
    })).json();
    const pub = await req([{ method: 'getPublishedLeagues', data: { sport: 'NBA' } }]);
    const leagueId = pub.responses[0].data.allLeagues[0].id;
    let rows = [], header = null, proj = null;
    for (let page = 1; page <= 20; page++) {
      const r = await req([{ method: 'getPlayerStats', data: {
        pageNumber: String(page), maxResultsPerPage: '250', statusOrTeamFilter: 'ALL', scoringCategoryType: '1' } }], leagueId);
      const d = r.responses[0].data;
      header = d.tableHeader.cells.map((c) => c.shortName || c.name);
      proj = d.displayedSelections.displayedSeasonOrProjection;
      for (const x of d.statsTable) {
        rows.push({ id: x.scorer.scorerId || x.scorer.id, name: x.scorer.name, team: x.scorer.teamShortName,
          pos: x.scorer.posShortNames, rookie: !!x.scorer.rookie, cells: x.cells.map((c) => c.content) });
      }
      window.__fantraxCapture.rows = rows.length;
      if (page >= d.paginatedResultSet.totalNumPages) break;
      await new Promise((ok) => setTimeout(ok, 1000));
    }
    if (!proj || proj.timeframeTypeCode !== 'PROJECTED_SEASON') throw new Error('not the season projection: ' + (proj && proj.code));
    const payload = { fetched_at: new Date().toISOString(), league_id: leagueId,
      projection: { code: proj.code, name: proj.name }, scoring_category_type: '1', header, rows };
    await fetch('http://localhost:8000/api/capture/fantrax-projections', {
      method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(payload) });
    window.__fantraxCapture = { state: 'done', rows: rows.length, projection: proj.code };
  } catch (e) {
    window.__fantraxCapture = { state: 'error', message: String(e) };
  }
})();
'started';

/**
 * TAwatch — Threat Watch corpus exporter
 *
 * Run this in browser DevTools console while on https://www.airiskexplorer.com/threats
 * It intercepts the page's own XHR/fetch calls to discover the data endpoint,
 * then downloads all incidents as JSONL ready for report/brain/tawatch_incidents.jsonl
 *
 * Usage:
 *   1. Open https://www.airiskexplorer.com/threats in Chrome/Firefox
 *   2. Open DevTools → Console
 *   3. Paste this entire script and press Enter
 *   4. Watch the console — it logs each page fetched
 *   5. When done, it triggers a download of tawatch_incidents.jsonl
 *   6. Place the file at: report/brain/tawatch_incidents.jsonl
 *   7. Reload corpus: POST /api/v1/tawatch/reload
 *
 * If auto-discovery fails, check the Network tab for XHR calls after filtering
 * the threats table, then update ENDPOINT below manually.
 */

(async () => {
  'use strict';

  // ── Step 1: intercept fetch to discover the actual data endpoint ───────────
  const _originalFetch = window.fetch;
  const _discovered = [];
  window.fetch = function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
    if (url && !url.includes('analytics') && !url.includes('favicon')) {
      _discovered.push(url);
      console.log('[TAwatch] fetch intercepted:', url);
    }
    return _originalFetch.apply(this, args);
  };

  // Trigger a scroll/filter to cause the page to load data
  console.log('[TAwatch] Triggering data load — waiting 3s...');
  window.scrollTo(0, 500);
  await new Promise(r => setTimeout(r, 3000));

  // Restore original fetch
  window.fetch = _originalFetch;

  const dataUrls = _discovered.filter(u =>
    u.includes('threat') || u.includes('incident') || u.includes('operation') || u.includes('api')
  );
  console.log('[TAwatch] Candidate data URLs:', dataUrls);

  if (dataUrls.length === 0) {
    console.warn('[TAwatch] No data endpoint auto-discovered. Check Network tab for XHR calls.');
    console.warn('[TAwatch] Look for a URL returning JSON with an array of threat/incident objects.');
    console.warn('[TAwatch] Then set ENDPOINT below and re-run from Step 2 onward.');
    return;
  }

  // ── Step 2: paginate through the endpoint and collect all incidents ────────
  // Update ENDPOINT if auto-discovery found it; otherwise set manually.
  const ENDPOINT = dataUrls[0];
  console.log('[TAwatch] Using endpoint:', ENDPOINT);

  const incidents = [];
  let page = 1;
  let totalPages = 1;

  while (page <= totalPages) {
    const sep = ENDPOINT.includes('?') ? '&' : '?';
    const url = `${ENDPOINT}${sep}page=${page}&limit=50`;
    console.log(`[TAwatch] Fetching page ${page}/${totalPages}...`);

    let data;
    try {
      const resp = await _originalFetch(url, { credentials: 'include' });
      data = await resp.json();
    } catch (err) {
      console.error('[TAwatch] Fetch error on page', page, err);
      break;
    }

    // Normalise different response shapes
    const rows = data.results || data.items || data.data || data.threats || data.incidents || (Array.isArray(data) ? data : []);
    if (rows.length === 0) break;

    for (const row of rows) {
      incidents.push(normalise(row));
    }

    // Try to infer total pages
    if (data.total && data.limit) {
      totalPages = Math.ceil(data.total / (data.limit || 50));
    } else if (data.total_pages) {
      totalPages = data.total_pages;
    } else if (data.next === null || data.next === undefined) {
      break;  // no next page signal
    }

    page++;
    await new Promise(r => setTimeout(r, 300)); // polite delay
  }

  console.log(`[TAwatch] Collected ${incidents.length} incidents.`);

  // ── Step 3: normalise a row into the TAwatch incident schema ──────────────
  function normalise(row) {
    return {
      id:             row.id || row.operation_id || row.slug || `op#${Math.random().toString(36).slice(2,7)}`,
      date:           row.date || row.reported_date || row.created_at || '',
      title:          row.title || row.name || row.headline || '',
      tactics:        toArray(row.tactics || row.mitre_tactics || row.attack_stages || []),
      capabilities:   toArray(row.capabilities || row.ai_capabilities || []),
      model:          row.model || row.model_family || row.ai_model || '',
      model_open:     row.model_open ?? row.open_weights ?? null,
      sector:         row.sector || row.target_sector || row.industry || '',
      actor_type:     row.actor_type || row.threat_actor_type || '',
      origin:         row.origin || row.actor_origin || row.country || '',
      sophistication: parseFloat(row.sophistication || row.sophistication_score || 0) || null,
      harm_type:      toArray(row.harm_type || row.harm_types || row.realized_harm || []),
      description:    row.description || row.summary || '',
      source_url:     row.source_url || row.source || row.url || '',
    };
  }

  function toArray(v) {
    if (!v) return [];
    if (Array.isArray(v)) return v.map(String);
    if (typeof v === 'string') return v.split(',').map(s => s.trim()).filter(Boolean);
    return [];
  }

  if (incidents.length === 0) {
    console.error('[TAwatch] No incidents collected. Check the endpoint and row structure.');
    return;
  }

  // ── Step 4: download as JSONL ──────────────────────────────────────────────
  const jsonl = incidents.map(i => JSON.stringify(i)).join('\n');
  const blob = new Blob([jsonl], { type: 'application/x-ndjson' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'tawatch_incidents.jsonl';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  console.log(`[TAwatch] Downloaded tawatch_incidents.jsonl (${incidents.length} incidents)`);
  console.log('[TAwatch] Place file at: report/brain/tawatch_incidents.jsonl');
  console.log('[TAwatch] Then reload: POST /api/v1/tawatch/reload');
})();

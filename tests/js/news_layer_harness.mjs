/* T13 — the browser half of news-to-globe, exercised in Node.
 *
 * `news_layer.js` holds the decisions about what the map draws, as a pure
 * function with no DOM and no THREE, exactly so they can be checked here
 * rather than asserted in a comment. The THREE drawing in index.html consumes
 * this plan and does no deciding of its own.
 *
 * Run: node tests/js/news_layer_harness.mjs
 */
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const componentDir = path.resolve(here, '../../seraph/dashboard/console_component');

const sandbox = { console };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(readFileSync(path.join(componentDir, 'news_layer.js'), 'utf8'),
                sandbox, { filename: 'news_layer.js' });

const NEWS = sandbox.SERAPH_NEWS;
const results = {};
const check = (name, value) => { results[name] = value; };

function node(id, lon, lat, layers, extra = {}) {
  return {
    node_id: id, coordinates: [lon, lat], coordinate_order: 'lon_lat',
    marker: extra.marker || 'dot',
    location_precision: extra.precision || 'city',
    layers, label: extra.label || id, events: extra.events || ['ev1'],
    mesh_id: extra.mesh || 'place_marker', status: 'derived'
  };
}

function payload(globe) {
  return { status: 'connected', globe: Object.assign({
    revision: 'r1', as_of: '2026-10-17T10:00:00+05:30',
    geometry_map_version: 'c12.globe_geometry/2026-10-17.1',
    nodes: [], edges: [], limitations: [],
    hidden_edges: { count: 0, edge_ids: [] },
    review_queue: { count: 0 }, layers: {}, details: {}
  }, globe) };
}

/* ---- an absent channel keeps the preview and says so ------------------ */
const absent = NEWS.plan({ status: 'absent', reason: 'nothing attached' });
check('absent_draws_nothing', absent.markers.length === 0 && absent.arcs.length === 0);
check('absent_keeps_preview', absent.previewVisible === true);
check('absent_banner_names_fabricated',
      NEWS.banner(absent).includes('FABRICATED PREVIEW'));
check('absent_never_says_live', !/live/i.test(NEWS.banner(absent)));

/* ---- a null payload is handled, not thrown on ------------------------- */
check('null_payload_is_safe', NEWS.plan(null).status === 'absent');
check('undefined_payload_is_safe', NEWS.plan(undefined).status === 'absent');

/* ---- evidenced nodes are drawn where the server put them -------------- */
const connected = NEWS.plan(payload({
  nodes: [node('place:us', -77.03, 38.9, ['origins'],
               { marker: 'outline', precision: 'country', label: 'United States' }),
          node('place:in-od', 85.0, 20.5, ['affected'],
               { marker: 'ring', precision: 'region', label: 'Odisha' })],
  edges: [{ edge_id: 'edge:1', from_node: 'place:us', to_node: 'place:in-od',
            mechanism: 'export', confidence: 'high', evidence_ids: ['ref:1'] }]
}));
check('nodes_drawn', connected.markers.length === 2);
check('coordinates_come_from_the_server',
      connected.markers[0].lon === -77.03 && connected.markers[0].lat === 38.9);
check('precision_survives',
      connected.markers.map(m => m.precision).join(',') === 'country,region');
check('marker_scale_differs_by_precision',
      connected.markers[0].scale !== connected.markers[1].scale);
check('arc_drawn_between_placed_endpoints', connected.arcs.length === 1);
check('arc_endpoints_are_the_node_positions',
      connected.arcs[0].from[0] === -77.03 && connected.arcs[0].to[0] === 85.0);

/* ---- palettes do not collide with the CSRS band ----------------------- */
const warmBand = [0xb7503f, 0xc9a63a, 0x6f9c7d, 0xc0392b, 0x7c5cbf];
check('news_palette_is_disjoint_from_the_csrs_band',
      [NEWS.COLOUR.origin, NEWS.COLOUR.affected, NEWS.COLOUR.path]
        .every(c => !warmBand.includes(c)));
check('origin_and_affected_are_different_colours',
      NEWS.COLOUR.origin !== NEWS.COLOUR.affected);
check('legend_names_each_live_layer',
      connected.legend.map(l => l.key).join(',') === 'origins,affected,paths');

/* ---- an origin that is also affected reads as an origin --------------- */
const both = NEWS.plan(payload({
  nodes: [node('place:x', 10, 10, ['affected', 'origins'])] }));
check('origin_wins_over_affected',
      both.markers[0].layer === 'origins' &&
      both.markers[0].colour === NEWS.COLOUR.origin);

/* ---- the subject of an instrument outranks a publisher's office ------- */
const subjectAndPublisher = NEWS.plan(payload({
  nodes: [node('cn', 105, 35, ['provenance', 'subjects', 'mentions'],
               { label: 'China' })] }));
check('subject_outranks_publisher_office',
      subjectAndPublisher.markers[0].layer === 'subjects' &&
      subjectAndPublisher.markers[0].colour === NEWS.COLOUR.subject);
check('subject_has_its_own_colour',
      NEWS.COLOUR.subject !== NEWS.COLOUR.origin &&
      NEWS.COLOUR.subject !== NEWS.COLOUR.affected &&
      NEWS.COLOUR.subject !== NEWS.COLOUR.mention);
check('subject_legend_claims_no_impact',
      subjectAndPublisher.legend.some(l =>
        l.key === 'subjects' && /covered by the instrument/.test(l.label)));

/* A documented exposure still says more than being named in an instrument. */
const affectedAndSubject = NEWS.plan(payload({
  nodes: [node('in', 79, 22, ['subjects', 'affected'])] }));
check('affected_outranks_subject',
      affectedAndSubject.markers[0].layer === 'affected');

/* ---- an unplaced endpoint is never substituted ------------------------ */
const dangling = NEWS.plan(payload({
  nodes: [node('place:in-od', 85.0, 20.5, ['affected'])],
  edges: [{ edge_id: 'edge:1', from_node: 'place:ghost',
            to_node: 'place:in-od', confidence: 'high', evidence_ids: [] }],
  review_queue: { count: 1 }
}));
check('arc_with_an_unplaced_endpoint_is_not_drawn', dangling.arcs.length === 0);
check('review_count_is_carried', dangling.reviewCount === 1);
check('banner_reports_the_review_queue',
      NEWS.banner(dangling).includes('review queue'));

/* ---- a node with no coordinates is skipped, not defaulted to 0,0 ------ */
const noCoords = NEWS.plan(payload({
  nodes: [{ node_id: 'place:y', layers: ['affected'], events: [] }] }));
check('a_node_without_coordinates_is_not_drawn_at_the_origin',
      noCoords.markers.length === 0);

/* ---- hidden edges are counted, not silently dropped ------------------- */
const hidden = NEWS.plan(payload({
  nodes: [node('a', 1, 1, ['origins']), node('b', 2, 2, ['affected'])],
  edges: [{ edge_id: 'e1', from_node: 'a', to_node: 'b', confidence: 'low',
            evidence_ids: [] }],
  hidden_edges: { count: 7, edge_ids: [] }
}));
check('hidden_edges_are_reported', hidden.hiddenEdges === 7);
check('hidden_is_not_absent_in_the_notes',
      hidden.notes.some(n => n.includes('hidden is not absent')));
check('banner_states_the_hidden_count',
      NEWS.banner(hidden).includes('7 hidden'));

/* ---- preview coexistence is stated, not implied ----------------------- */
const withPreview = NEWS.plan(payload({
  nodes: [node('a', 1, 1, ['origins'])],
  layers: { preview: { status: 'preview', fabricated: true } }
}));
check('preview_coexistence_is_visible', withPreview.previewVisible === true);
check('banner_states_the_combination',
      NEWS.banner(withPreview).includes('FABRICATED illustrative layer'));

/* ---- arcs do not animate until asked ---------------------------------- */
check('arcs_are_static_until_selected',
      connected.arcs.every(a => a.animate === false));

/* ---- the plan is deterministic ---------------------------------------- */
const a1 = JSON.stringify(NEWS.plan(payload({
  nodes: [node('a', 1, 1, ['origins']), node('b', 2, 2, ['affected'])] })));
const a2 = JSON.stringify(NEWS.plan(payload({
  nodes: [node('a', 1, 1, ['origins']), node('b', 2, 2, ['affected'])] })));
check('plan_is_deterministic', a1 === a2);

console.log(JSON.stringify(results, null, 2));
const failed = Object.entries(results).filter(([, v]) => v !== true);
if (failed.length) {
  console.error('FAILED: ' + failed.map(([k]) => k).join(', '));
  process.exit(1);
}
console.log('news layer harness: ' + Object.keys(results).length + ' checks passed');

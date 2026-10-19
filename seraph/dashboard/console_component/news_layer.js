/* C12 — evidenced news layer for the globe (T13; audit findings R07/R08).
 *
 * The decisions about WHAT to draw live here as a pure function, with no DOM
 * and no THREE, so they can be tested in Node the way the bridge is. The
 * drawing itself lives in index.html where the scene is. One more place that
 * could decide a node's position would be one more place that could disagree
 * with the server about where evidence puts it.
 *
 * Three rules this file exists to keep:
 *
 *   1. The server places nodes. `plan()` reads `coordinates` and
 *      `location_precision` from the payload and never computes a fallback
 *      position. A node the server could not place is reported as a review
 *      item, not drawn at a guess.
 *   2. Evidenced layers and the fabricated preview never share a palette.
 *      News colours are cool (origin cyan, affected violet, path slate);
 *      CSRS and the preview keep the warm amber/red identity. A "negative"
 *      news mechanism must not read as a red risk score.
 *   3. What is hidden is counted. Bounded edge drawing is legibility, not
 *      evidence, and the legend says how many were held back.
 */
(function (root) {

  var VERSION = 'c12.news_layer/2026-10-17.1';

  /* Cool palette — deliberately disjoint from the CSRS amber/red band. */
  var COLOUR = {
    origin:   0x5aa9c9,
    affected: 0x9b7bd4,
    path:     0x7f8da3,
    pathHot:  0xb9c6d8,
    /* Deliberately the dimmest: a mention claims the least. */
    mention:  0x5c6b78,
    /* The subject of an instrument: evidenced, and not yet an impact. */
    subject:  0x7fb8a0
  };

  var MARKER_SCALE = { pin: 1.0, dot: 0.9, ring: 1.6, outline: 2.4 };

  function layerOf(node) {
    /* A node can sit in several layers at once. The order below is the order
       of how much is CLAIMED: an origin is evidenced by source registration,
       an affected location by a documented relationship, and a mention by
       nothing more than the word appearing. The strongest claim wins the
       colour, so a mere mention is never drawn as an impact. */
    var layers = node.layers || [];
    /* Only ONE change to the inherited order: `subjects` now outranks
       `provenance`. A publisher's office is a fact about the PUBLISHER; a
       subject origin is a fact about the INSTRUMENT. When a country is both
       — China publishes the measure and its goods are its subject —
       captioning it "a publisher's office is here" loses the role the map
       exists to show, and both are equally evidenced.

       Origin still beats affected: a source of a development is never drawn
       as one of its victims. And affected still beats subjects: a documented
       exposure reaching a place says more than the place being named in an
       instrument. */
    if (layers.indexOf('origins') >= 0) return 'origins';
    if (layers.indexOf('affected') >= 0) return 'affected';
    if (layers.indexOf('subjects') >= 0) return 'subjects';
    if (layers.indexOf('provenance') >= 0) return 'provenance';
    if (layers.indexOf('mentions') >= 0) return 'mentions';
    return layers[0] || 'mentions';
  }

  function colourFor(layer) {
    if (layer === 'provenance') return COLOUR.origin;
    if (layer === 'origins') return COLOUR.origin;
    if (layer === 'affected') return COLOUR.affected;
    if (layer === 'subjects') return COLOUR.subject;
    return COLOUR.mention;
  }

  /* Decide the whole layer from the payload. Pure: same input, same plan. */
  function plan(news) {
    if (!news || news.status === 'absent' || !news.globe) {
      return {
        version: VERSION, status: 'absent', markers: [], arcs: [],
        reviewCount: 0, hiddenEdges: 0, previewVisible: true,
        legend: [],
        notes: [(news && news.reason) ||
                'no news channel is attached; the illustrative map is all ' +
                'that is shown and it is labelled FABRICATED']
      };
    }

    var globe = news.globe;
    if(news.context && (news.context.news_as_of!==globe.as_of ||
       JSON.stringify(news.context)!==JSON.stringify(globe.context)))
      throw new Error('news clock/context mismatch');
    var nodes = globe.nodes || [];
    var edges = globe.edges || [];
    var byId = {};
    var markers = [];

    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!n.coordinates || n.coordinates.length !== 2) continue;
      var layer = layerOf(n);
      var marker = {
        node_id: n.node_id,
        lon: n.coordinates[0],
        lat: n.coordinates[1],
        marker: n.marker || 'dot',
        scale: MARKER_SCALE[n.marker] || 1.0,
        precision: n.location_precision,
        layer: layer,
        colour: colourFor(layer),
        label: n.label || n.node_id,
        events: (n.events || []).length,
        meshId: n.mesh_id
      };
      markers.push(marker);
      byId[n.node_id] = marker;
    }

    var arcs = [];
    for (var k = 0; k < edges.length; k++) {
      var e = edges[k];
      var a = byId[e.from_node], b = byId[e.to_node];
      /* An arc whose endpoint was not placed is not drawn at a substitute
         position. The server already put that endpoint in the review queue. */
      if (!a || !b) continue;
      arcs.push({
        edge_id: e.edge_id,
        from: [a.lon, a.lat],
        to: [b.lon, b.lat],
        colour: COLOUR.path,
        hot: COLOUR.pathHot,
        confidence: e.confidence,
        mechanism: e.mechanism,
        /* Animate only what the viewer has asked about. Everything pulsing at
           once reads as urgency the evidence does not support. */
        animate: false
      });
    }

    var legend = [];
    if(markers.some(function(m){return m.layer==='provenance';}))
      legend.push({key:'provenance',label:'publisher / issuer provenance (not occurrence)',colour:COLOUR.origin});
    if (markers.some(function (m) { return m.layer === 'origins'; })) {
      legend.push({ key: 'origins', label: 'event origin',
                    colour: COLOUR.origin });
    }
    if (markers.some(function (m) { return m.layer === 'affected'; })) {
      legend.push({ key: 'affected',
                    label: 'potentially affected location or asset',
                    colour: COLOUR.affected });
    }
    if (markers.some(function (m) { return m.layer === 'subjects'; })) {
      legend.push({ key: 'subjects',
                    label: 'goods from here are covered by the instrument',
                    colour: COLOUR.subject });
    }
    if (markers.some(function (m) { return m.layer === 'mentions'; })) {
      legend.push({ key: 'mentions',
                    label: 'named in the story — role not established',
                    colour: COLOUR.mention });
    }
    if (arcs.length) {
      legend.push({ key: 'paths', label: 'documented transmission path',
                    colour: COLOUR.path });
    }

    var notes = (globe.limitations || []).slice();
    var hidden = (globe.hidden_edges || {}).count || 0;
    if (hidden) {
      notes.push(hidden + ' documented path(s) hidden for legibility; ' +
                 'hidden is not absent');
    }

    return {
      version: VERSION,
      status: markers.length || arcs.length ? 'connected' : 'empty',
      markers: markers,
      arcs: arcs,
      reviewCount: (globe.review_queue || {}).count || 0,
      hiddenEdges: hidden,
      /* The preview stays on screen whenever it is supplied, and the caller
         is told to say so. Deleting the original identity was never the fix. */
      previewVisible: !!(globe.layers && globe.layers.preview &&
                         globe.layers.preview.status === 'preview'),
      legend: legend,
      notes: notes,
      asOf: globe.as_of,
      revision: globe.revision,
      geometryMapVersion: globe.geometry_map_version
    };
  }

  /* The one-line banner above the map. It must never say "live" for a
     fabricated layer, and never hide that the two can be on screen together. */
  function banner(p) {
    if (p.status === 'absent') {
      return 'NEWS CHANNEL NOT CONNECTED · illustrative map only ' +
             '(FABRICATED PREVIEW)';
    }
    var bits = [];
    bits.push(p.markers.length + ' evidenced node' +
              (p.markers.length === 1 ? '' : 's'));
    bits.push(p.arcs.length + ' documented path' +
              (p.arcs.length === 1 ? '' : 's'));
    if (p.reviewCount) bits.push(p.reviewCount + ' unplaced (review queue)');
    if (p.hiddenEdges) bits.push(p.hiddenEdges + ' hidden');
    var text = bits.join(' · ');
    if (p.previewVisible) {
      text += ' · shown together with the FABRICATED illustrative layer';
    }
    return text;
  }

  root.SERAPH_NEWS = { VERSION: VERSION, COLOUR: COLOUR, plan: plan,
                       banner: banner };

})(typeof window !== 'undefined' ? window :
   (typeof globalThis !== 'undefined' ? globalThis : this));

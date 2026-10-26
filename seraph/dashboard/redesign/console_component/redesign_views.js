/* Redesigned views, hosted inside the existing console shell.
 *
 * The console IS the product's UI, so the redesigned screens are entries in
 * its own nav rather than a separate app with the console embedded in it.
 * This file is the only addition to the forked component: `bridge.js` calls
 * `render` when one of these views is selected and `bind` afterwards.
 *
 * WHY THE HTML COMES FROM PYTHON. The dial, the contribution tracks and the
 * timeline are already built, tested and honest in `redesign/instruments.py`
 * -- including the rules that an unavailable score keeps its track unfilled
 * and that a mask-excluded pillar is never drawn as a measured zero. Writing
 * a second implementation of those in JavaScript would be a second place for
 * them to be wrong. So Python renders each view to a markup string, the
 * payload carries it, and this file injects it and wires the controls.
 *
 * BINDING IS DECLARATIVE. A control carries its operation and its inputs as
 * data attributes, so Python emits plain markup and nothing here needs to
 * know what a particular form means:
 *
 *   data-rd-op="ws_create"              the operation to request
 *   data-rd-field-name="rd-new-name"    args.name   = value of #rd-new-name
 *   data-rd-const-kind="rank_shock"     args.kind   = "rank_shock"
 *   data-rd-json-steps="rd-steps"       args.steps  = JSON.parse(#rd-steps)
 *   data-rd-file-body="rd-upload"       args.body   = text of the chosen file
 *
 * Every operation goes out through the console's own `request()`, so it gets
 * the same idempotency id, the same in-flight status line and the same
 * stale-context refusal as every other operation in the console.
 */
(function () {
  'use strict';

  /* The views this file owns. `bridge.js` checks membership before calling. */
  var VIEWS = ['current', 'overview', 'warning', 'workspace',
               'evaluation', 'health'];

  function markup(data, view) {
    var rd = (data && data.redesign) || {};
    var views = rd.views || {};
    if (Object.prototype.hasOwnProperty.call(views, view)) return views[view];
    /* Absence is reported, never papered over with an empty panel. */
    return '<div class="rd-unavail"><p class="rd-unavail-label">view not '
      + 'supplied</p><p class="rd-reason">the payload carries no markup for '
      + '"' + view + '". That is a defect in the projection, not an empty '
      + 'result, and it is shown rather than rendered as a blank panel.</p>'
      + '</div>';
  }

  /* Read one argument off a control's data attributes. */
  function collect(el) {
    var args = {};
    var pending = [];
    for (var i = 0; i < el.attributes.length; i++) {
      var attr = el.attributes[i];
      var name = attr.name;
      var m;
      if ((m = name.match(/^data-rd-const-(.+)$/))) {
        args[m[1]] = attr.value;
      } else if ((m = name.match(/^data-rd-field-(.+)$/))) {
        var node = document.getElementById(attr.value);
        args[m[1]] = node ? node.value : '';
      } else if ((m = name.match(/^data-rd-number-(.+)$/))) {
        var num = document.getElementById(attr.value);
        args[m[1]] = num ? Number(num.value) : null;
      } else if ((m = name.match(/^data-rd-json-(.+)$/))) {
        var raw = document.getElementById(attr.value);
        /* Let a parse error throw: the caller turns it into a visible
           "input rejected" status rather than sending malformed args. */
        args[m[1]] = raw ? JSON.parse(raw.value) : null;
      } else if ((m = name.match(/^data-rd-file-(.+)$/))) {
        pending.push({ key: m[1], id: attr.value });
      }
    }
    return { args: args, files: pending };
  }

  function readFile(input) {
    return new Promise(function (resolve, reject) {
      if (!input || !input.files || !input.files.length) {
        resolve(null);
        return;
      }
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result)); };
      reader.onerror = function () { reject(reader.error); };
      reader.readAsText(input.files[0]);
    });
  }

  /* `request` and `setStatus` are the console's own, passed in by bridge.js
     so these controls behave exactly like the ones already in TOOLS. */
  function bind(view, api) {
    var request = api.request;
    var setStatus = api.setStatus || function () {};
    var root = document.getElementById('extra-content');
    if (!root) return;

    var controls = root.querySelectorAll('[data-rd-op]');
    for (var i = 0; i < controls.length; i++) {
      (function (el) {
        el.onclick = function (event) {
          if (event && event.preventDefault) event.preventDefault();
          var op = el.getAttribute('data-rd-op');
          var picked;
          try {
            picked = collect(el);
          } catch (err) {
            setStatus('failed', 'input rejected: ' + err.message);
            return;
          }
          if (!picked.files.length) {
            request(op, picked.args);
            return;
          }
          /* A file-bearing control resolves its reads first, so the request
             carries the body rather than a promise. */
          var reads = picked.files.map(function (f) {
            return readFile(document.getElementById(f.id)).then(function (text) {
              picked.args[f.key] = text;
            });
          });
          Promise.all(reads).then(function () {
            for (var k = 0; k < picked.files.length; k++) {
              if (picked.args[picked.files[k].key] == null) {
                setStatus('failed', 'choose a file first');
                return;
              }
            }
            request(op, picked.args);
          }).catch(function (err) {
            setStatus('failed', 'could not read the file: ' + err.message);
          });
        };
      })(controls[i]);
    }

    /* Selection controls re-project rather than compute: changing the run,
       the date, the sector basis or the news clock is a different question,
       not a new calculation. */
    var selects = root.querySelectorAll('[data-rd-select]');
    for (var j = 0; j < selects.length; j++) {
      (function (el) {
        el.onchange = function () {
          request('rd_select', { field: el.getAttribute('data-rd-select'),
                                 value: el.value });
        };
      })(selects[j]);
    }
  }


  /* ---------------------------------------------------------------------
   * decorate(data) — panels outside #extra-content.
   *
   * The forked console shipped three cards that no script ever wrote to:
   * INPUT COMMODITIES, METEOROLOGICAL INPUTS and STRATEGIC ASSETS, plus a
   * footer crawl labelled FABRICATED NEWS PREVIEW. The first two have no
   * engine anywhere in SERAPH and were removed from the fork rather than
   * relabelled -- a prettier label on invented numbers is still invented
   * numbers. The other two DO have a real source: the news channel carries
   * a registered-asset surface and the eligible-event rail. So they are
   * wired to it here.
   *
   * With the channel detached these say so. "Not attached to this view" is
   * a different statement from "fabricated", and it is the true one.
   * ------------------------------------------------------------------- */
  function text(el, value) { if (el) el.textContent = value; }


  /* Which card a surface backs, by an element inside it. A card whose
   * surface is CONNECTED carries real data and must lose the blanket
   * FABRICATED tag that bridge.js stamps on every card at load -- before
   * any payload has arrived, so it cannot know. bridge.js's own comment
   * says why that is wrong: a tag above real Federal Register headlines
   * with working source links teaches the viewer to ignore the tag, and
   * the tag is the thing that has to keep working.
   *
   * A surface that is NOT connected keeps its tag. This only removes the
   * claim where the payload says the data is real.
   */
  var SURFACE_OF = {
    signals: 'signals',
    stress: 'sector_stress',
    assets: 'assets'
  };

  function retagCards(news) {
    var connected = (news && news.connected_surfaces) || [];
    var attached = news && (news.status === 'connected' || news.status === 'empty');
    for (var id in SURFACE_OF) {
      if (!Object.prototype.hasOwnProperty.call(SURFACE_OF, id)) continue;
      var el = document.getElementById(id);
      if (!el) continue;
      var card = el.closest ? el.closest('.card') : null;
      if (!card) continue;
      var heading = card.querySelector('h3');
      if (!heading) continue;
      var real = attached && connected.indexOf(SURFACE_OF[id]) >= 0;
      var tags = heading.querySelectorAll('.fabricated');
      for (var i = 0; i < tags.length; i++) {
        if (real) tags[i].remove();
        else tags[i].textContent = 'NOT ATTACHED';
      }
      /* The sector card also carries a static "NEWS ESTIMATE · FABRICATED"
         label in the markup; it is an estimate either way, but it stops
         being fabricated once a real channel is behind it. */
      var statics = heading.querySelectorAll('span.r');
      for (var j = 0; j < statics.length; j++) {
        var txt = statics[j].textContent || '';
        if (txt.indexOf('FABRICATED') >= 0) {
          statics[j].textContent = real
            ? 'NEWS ESTIMATE · DOCUMENTED ROUTES'
            : 'NEWS ESTIMATE · NOT ATTACHED';
        }
      }
    }
  }

  function decorate(data) {
    var news = (data && data.news) || {};
    var attached = news.status === 'connected' || news.status === 'empty';
    var surfaces = news.surfaces || {};
    retagCards(news);

    /* --- STRATEGIC ASSETS: the registered facilities the channel knows --- */
    var assetBody = document.getElementById('assets');
    var assetCount = document.getElementById('acount');
    var items = ((surfaces.assets || {}).items) || [];
    if (assetBody) {
      if (!attached) {
        assetBody.innerHTML = '<p class="rd-reason">News channel not attached '
          + 'to this view, so no registered assets are listed. That is a '
          + 'property of this view, not of the channel.</p>';
        text(assetCount, 'NOT ATTACHED');
      } else if (!items.length) {
        assetBody.innerHTML = '<p class="rd-reason">No registered asset is '
          + 'referenced by an eligible event at this clock. An empty result, '
          + 'not a missing one.</p>';
        text(assetCount, '0 SITES');
      } else {
        assetBody.innerHTML = items.slice(0, 40).map(function (a) {
          var cap = (a.capacity == null) ? ''
            : (' · ' + a.capacity + ' ' + (a.capacity_unit || ''));
          return '<div class="ckv"><span>' + esc(a.name || a.asset_id)
            + '</span><b>' + esc(a.kind || '') + cap + '</b></div>';
        }).join('');
        text(assetCount, items.length + ' SITES');
      }
    }

    /* --- the footer crawl: real headlines, or an honest absence --- */
    var crawl = document.getElementById('crawl');
    var label = document.getElementById('crawl-label');
    var signals = ((surfaces.signals || {}).items) || [];
    if (crawl) {
      if (!attached) {
        crawl.textContent = 'News channel not attached to this view — '
          + 'switch the news layer on to stream eligible events here.';
        text(label, 'NEWS CHANNEL NOT ATTACHED');
      } else if (!signals.length) {
        crawl.textContent = 'No eligible event at this clock.';
        text(label, 'NEWS CHANNEL · EMPTY');
      } else {
        crawl.textContent = signals.slice(0, 30).map(function (s) {
          return (s.event_type || 'event').toUpperCase() + ' — '
            + (s.headline || '');
        }).join('   ·   ');
        var total = (news.pagination || {}).total;
        text(label, 'NEWS CHANNEL · LIVE'
          + (total ? ' · ' + total + ' ELIGIBLE EVENTS' : ''));
      }
    }
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  window.SERAPH_REDESIGN = {
    views: VIEWS,
    owns: function (view) { return VIEWS.indexOf(view) >= 0; },
    render: function (view, data) { return markup(data, view); },
    bind: bind,
    decorate: decorate
  };
})();

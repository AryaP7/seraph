/* SERAPH globe core — shared by the browser build and the offline render check.
   Exposes buildSeraphGlobe(THREE, DATA, cfg). No DOM access in here. */
(function (root) {

var D2R = Math.PI / 180;

/* Sphere mapping: +Y is the north pole. lon/lat degrees -> world XYZ. */
function toXYZ(lon, lat, r) {
  var p = (90 - lat) * D2R;
  var t = (lon + 180) * D2R;
  return [
    -r * Math.sin(p) * Math.cos(t),
     r * Math.cos(p),
     r * Math.sin(p) * Math.sin(t)
  ];
}

/* Insert intermediate vertices so a boundary hugs the sphere instead of
   cutting a chord through it. */
function densify(ring, stepDeg) {
  var out = [];
  for (var i = 0; i < ring.length - 1; i++) {
    var a = ring[i], b = ring[i + 1];
    var dx = b[0] - a[0], dy = b[1] - a[1];
    var n = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / stepDeg));
    for (var k = 0; k < n; k++) out.push([a[0] + dx * k / n, a[1] + dy * k / n]);
  }
  out.push(ring[ring.length - 1]);
  return out;
}

/* Triangulate a lon/lat ring, then split any triangle with an edge longer than
   maxDeg so the flat facets stay above the sphere surface. */
function triangulate(THREE, ring, maxDeg) {
  var c = ring.slice(0, ring.length - 1).map(function (p) {
    return new THREE.Vector2(p[0], p[1]);
  });
  if (c.length < 3) return [];
  var idx = THREE.ShapeUtils.triangulateShape(c, []);
  var tris = idx.map(function (t) {
    return [[c[t[0]].x, c[t[0]].y], [c[t[1]].x, c[t[1]].y], [c[t[2]].x, c[t[2]].y]];
  });

  function elen(a, b) { return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])); }
  for (var pass = 0; pass < 6; pass++) {
    var next = [], split = false;
    for (var i = 0; i < tris.length; i++) {
      var t = tris[i];
      if (Math.max(elen(t[0], t[1]), elen(t[1], t[2]), elen(t[2], t[0])) > maxDeg) {
        split = true;
        var m01 = [(t[0][0] + t[1][0]) / 2, (t[0][1] + t[1][1]) / 2];
        var m12 = [(t[1][0] + t[2][0]) / 2, (t[1][1] + t[2][1]) / 2];
        var m20 = [(t[2][0] + t[0][0]) / 2, (t[2][1] + t[0][1]) / 2];
        next.push([t[0], m01, m20], [m01, t[1], m12], [m20, m12, t[2]], [m01, m12, m20]);
      } else next.push(t);
    }
    tris = next;
    if (!split) break;
  }
  return tris;
}

/* Same as triangulate() but honours interior rings, so a landlocked non-member
   like Switzerland stays a hole in the EU fill instead of being painted over. */
function triangulateWithHoles(THREE, rec, maxDeg) {
  var o = rec.o || rec;
  var holes = rec.h || [];
  if (!holes.length) return triangulate(THREE, o, maxDeg);

  var contour = o.slice(0, o.length - 1).map(function (p) { return new THREE.Vector2(p[0], p[1]); });
  var hpaths = holes.map(function (h) {
    return h.slice(0, h.length - 1).map(function (p) { return new THREE.Vector2(p[0], p[1]); });
  });
  if (contour.length < 3) return [];

  var all = contour.slice();
  for (var i = 0; i < hpaths.length; i++) all = all.concat(hpaths[i]);
  var faces = THREE.ShapeUtils.triangulateShape(contour, hpaths);
  var tris = faces.map(function (f) {
    return [[all[f[0]].x, all[f[0]].y], [all[f[1]].x, all[f[1]].y], [all[f[2]].x, all[f[2]].y]];
  });

  function elen(a, b) { return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])); }
  for (var pass = 0; pass < 6; pass++) {
    var next = [], split = false;
    for (var t = 0; t < tris.length; t++) {
      var tr = tris[t];
      if (Math.max(elen(tr[0], tr[1]), elen(tr[1], tr[2]), elen(tr[2], tr[0])) > maxDeg) {
        split = true;
        var m01 = [(tr[0][0] + tr[1][0]) / 2, (tr[0][1] + tr[1][1]) / 2];
        var m12 = [(tr[1][0] + tr[2][0]) / 2, (tr[1][1] + tr[2][1]) / 2];
        var m20 = [(tr[2][0] + tr[0][0]) / 2, (tr[2][1] + tr[0][1]) / 2];
        next.push([tr[0], m01, m20], [m01, tr[1], m12], [m20, m12, tr[2]], [m01, m12, m20]);
      } else next.push(tr);
    }
    tris = next;
    if (!split) break;
  }
  return tris;
}

function trisToGeometry(THREE, tris, radius) {
  var pos = new Float32Array(tris.length * 9);
  var o = 0;
  for (var i = 0; i < tris.length; i++) {
    for (var v = 0; v < 3; v++) {
      var p = toXYZ(tris[i][v][0], tris[i][v][1], radius);
      pos[o++] = p[0]; pos[o++] = p[1]; pos[o++] = p[2];
    }
  }
  var g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

/* Merged line segments for a batch of rings — one draw call for the lot. */
function ringsToLines(THREE, rings, radius, stepDeg) {
  var pts = [];
  for (var i = 0; i < rings.length; i++) {
    var d = densify(rings[i], stepDeg);
    for (var k = 0; k < d.length - 1; k++) {
      var a = toXYZ(d[k][0], d[k][1], radius);
      var b = toXYZ(d[k + 1][0], d[k + 1][1], radius);
      pts.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
  }
  var g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts), 3));
  return g;
}

/* A state lifted radially off the globe: top cap plus side wall.
   Height is along the sphere normal, so "up" is unambiguous by construction. */
function radialPrism(THREE, ring, rBase, rTop, maxDeg) {
  var top = triangulate(THREE, ring, maxDeg);
  var pos = [];
  for (var i = 0; i < top.length; i++) {
    for (var v = 0; v < 3; v++) {
      var p = toXYZ(top[i][v][0], top[i][v][1], rTop);
      pos.push(p[0], p[1], p[2]);
    }
  }
  var wall = densify(ring, maxDeg);
  for (var k = 0; k < wall.length - 1; k++) {
    var a = wall[k], b = wall[k + 1];
    var a0 = toXYZ(a[0], a[1], rBase), a1 = toXYZ(a[0], a[1], rTop);
    var b0 = toXYZ(b[0], b[1], rBase), b1 = toXYZ(b[0], b[1], rTop);
    pos.push(a0[0], a0[1], a0[2], b0[0], b0[1], b0[2], a1[0], a1[1], a1[2]);
    pos.push(b0[0], b0[1], b0[2], b1[0], b1[1], b1[2], a1[0], a1[1], a1[2]);
  }
  var g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pos), 3));
  g.computeVertexNormals();
  return g;
}


/* Tileable fBm cloud field. Returns RGBA bytes: white with noise in alpha.
   Wraps seamlessly in longitude so there is no visible seam at the date line. */
function hash2(ix, iy, seed) {
  /* Math.imul keeps every product inside 32 bits. Plain * overflows 2^53 on
     the second multiply and the hash stops being uniform. */
  var h = Math.imul(ix, 374761393) ^ Math.imul(iy, 668265263) ^ Math.imul(seed, 1442695041);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
function vnoise(x, y, per, seed) {
  var x0 = Math.floor(x), y0 = Math.floor(y);
  var fx = x - x0, fy = y - y0;
  var ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
  var xa = ((x0 % per) + per) % per, xb = ((x0 + 1) % per + per) % per;
  var a = hash2(xa, y0, seed),     b = hash2(xb, y0, seed);
  var c = hash2(xa, y0 + 1, seed), d = hash2(xb, y0 + 1, seed);
  return (a * (1 - ux) + b * ux) * (1 - uy) + (c * (1 - ux) + d * ux) * uy;
}
function makeCloudData(W, H, seed, cover) {
  cover = cover === undefined ? 0.44 : cover;
  var data = new Uint8Array(W * H * 4);
  var basePer = 12;
  for (var y = 0; y < H; y++) {
    var lat = 90 - (y / (H - 1)) * 180;
    /* ITCZ + mid-latitude storm tracks: more cloud near 0 and +/-55 deg */
    var band = 0.55
      + 0.60 * Math.exp(-Math.pow(lat / 11, 2))
      + 0.50 * Math.exp(-Math.pow((Math.abs(lat) - 56) / 14, 2))
      - 0.42 * Math.exp(-Math.pow((Math.abs(lat) - 27) / 11, 2));
    for (var x = 0; x < W; x++) {
      var amp = 0.5, freq = 1, sum = 0, norm = 0;
      for (var o = 0; o < 7; o++) {
        var per = basePer * freq;
        sum += amp * vnoise(x / W * per, y / H * per * 0.5, per, seed + o * 37);
        norm += amp; amp *= 0.62; freq *= 2;
      }
      var n = sum / norm;
      /* Latitude bands shift the threshold rather than scaling the field, so
         the cloud field keeps its full contrast everywhere. */
      var thr = cover + 0.17 * (1 - band);
      var v = (n - thr) / 0.135;
      v = v <= 0 ? 0 : (v >= 1 ? 1 : v * v * (3 - 2 * v));
      var i = (y * W + x) * 4;
      data[i] = 255; data[i + 1] = 255; data[i + 2] = 255;
      data[i + 3] = Math.round(v * 232);
    }
  }
  return data;
}

/* Mean unit vector of a set of rings. Averaging lon/lat directly breaks for
   anything crossing the date line (the US, with Alaska, is the obvious case);
   averaging the 3D directions does not. */
function ringsDirection(rings) {
  var x = 0, y = 0, z = 0, n = 0;
  for (var i = 0; i < rings.length; i++) {
    var ring = rings[i];
    for (var k = 0; k < ring.length - 1; k++) {
      var p = toXYZ(ring[k][0], ring[k][1], 1);
      x += p[0]; y += p[1]; z += p[2]; n++;
    }
  }
  var L = Math.sqrt(x * x + y * y + z * z) || 1;
  return [x / L, y / L, z / L];
}

function ringCentroid(ring) {
  var x = 0, y = 0, n = ring.length - 1;
  for (var i = 0; i < n; i++) { x += ring[i][0]; y += ring[i][1]; }
  return [x / n, y / n];
}


/* ---------------------------------------------------------------- holograms */
/* A physical asset marker standing on the sphere: base ring flat on the
   surface, a light beam along the surface normal, a spinning gimbal ring and a
   node at the top. Oriented by rotating local +Y onto the surface normal, so
   there is no per-asset euler maths to get wrong. */
/* ---------------------------------------------------------------------------
   Sector-specific site models, built from primitives. These are solid objects
   standing on the globe, not glowing markers: a steel works reads as furnace +
   stacks, a solar park as a tilted panel array, and so on. Every model is
   authored with +Y as up and its base at y = 0; the caller rotates the whole
   group so +Y aligns with the surface normal.
--------------------------------------------------------------------------- */
function matFor(THREE, col, disposables, opts) {
  opts = opts || {};
  var m = new THREE.MeshPhongMaterial({
    color: col,
    emissive: opts.emissive === undefined ? col : opts.emissive,
    emissiveIntensity: opts.ei === undefined ? 0.42 : opts.ei,
    shininess: opts.shininess === undefined ? 22 : opts.shininess,
    specular: 0x1a1a1c
  });
  disposables.push(m);
  return m;
}

function addMesh(THREE, parent, geo, mat, x, y, z, rx, ry, rz, disposables) {
  var m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  if (rx) m.rotation.x = rx;
  if (ry) m.rotation.y = ry;
  if (rz) m.rotation.z = rz;
  parent.add(m);
  disposables.push(geo);
  return m;
}

function siteModel(THREE, type, col, S, disposables) {
  var g = new THREE.Group();
  var body = matFor(THREE, col, disposables);
  var dark = matFor(THREE, 0x5d646d, disposables, { emissive: 0x282c31, ei: 0.22 });
  var hot  = matFor(THREE, 0xff7a2f, disposables, { emissive: 0xff7a2f, ei: 0.85, shininess: 4 });
  var A = addMesh;

  if (type === "steel") {
    /* squat furnace + bustle ring + two flue stacks + cast house */
    A(THREE, g, new THREE.BoxGeometry(1.55*S, 0.12*S, 1.05*S), dark, 0, 0.06*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.44*S, 0.56*S, 1.10*S, 12), body, -0.34*S, 0.67*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.TorusGeometry(0.56*S, 0.075*S, 6, 16), dark, -0.34*S, 0.78*S, 0, Math.PI/2,0,0, disposables);
    A(THREE, g, new THREE.ConeGeometry(0.44*S, 0.34*S, 12), body, -0.34*S, 1.39*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.10*S, 0.10*S, 0.30*S, 8), dark, -0.34*S, 1.68*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.12*S, 0.15*S, 2.00*S, 8), dark, 0.62*S, 1.00*S, -0.34*S, 0,0,0, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.10*S, 0.13*S, 1.55*S, 8), dark, 0.86*S, 0.78*S, 0.26*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.62*S, 0.42*S, 0.80*S), dark, 0.30*S, 0.27*S, 0.42*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.34*S, 0.14*S, 0.34*S), hot, -0.34*S, 0.19*S, 0.44*S, 0,0,0, disposables);

  } else if (type === "solar") {
    /* three tilted panel banks on posts */
    var tilt = -35 * Math.PI / 180;
    for (var i = 0; i < 3; i++) {
      var z = (i - 1) * 0.62 * S;
      A(THREE, g, new THREE.BoxGeometry(1.9*S, 0.05*S, 0.52*S), body, 0, 0.52*S, z, tilt,0,0, disposables);
      A(THREE, g, new THREE.CylinderGeometry(0.04*S, 0.04*S, 0.42*S, 6), dark, -0.6*S, 0.21*S, z, 0,0,0, disposables);
      A(THREE, g, new THREE.CylinderGeometry(0.04*S, 0.04*S, 0.42*S, 6), dark,  0.6*S, 0.21*S, z, 0,0,0, disposables);
    }
    A(THREE, g, new THREE.BoxGeometry(0.42*S, 0.46*S, 0.42*S), dark, 1.35*S, 0.23*S, 0, 0,0,0, disposables);

  } else if (type === "auto") {
    /* assembly shed with sawtooth roof + a gear facing the viewer */
    A(THREE, g, new THREE.BoxGeometry(1.30*S, 0.52*S, 0.95*S), dark, -0.72*S, 0.26*S, 0, 0,0,0, disposables);
    for (var k = 0; k < 3; k++) {
      A(THREE, g, new THREE.BoxGeometry(0.42*S, 0.05*S, 0.95*S), body,
        (-1.16 + k*0.44)*S, 0.62*S, 0, 0, 0, -30*Math.PI/180, disposables);
    }
    /* gear axis along Z so the face points at the camera; teeth must therefore
       be laid out in the XY plane. Putting them in the YZ plane (the earlier
       bug) leaves them floating beside the rim instead of on it. */
    var gearR = 0.62*S, gx = 0.78*S, gy = 0.86*S;
    A(THREE, g, new THREE.CylinderGeometry(gearR, gearR, 0.20*S, 20), body, gx, gy, 0, Math.PI/2, 0, 0, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.20*S, 0.20*S, 0.26*S, 12), dark, gx, gy, 0, Math.PI/2, 0, 0, disposables);
    for (var q = 0; q < 8; q++) {
      var th = q / 8 * Math.PI * 2;
      A(THREE, g, new THREE.BoxGeometry(0.24*S, 0.24*S, 0.20*S), body,
        gx + Math.cos(th)*gearR, gy + Math.sin(th)*gearR, 0, 0, 0, th, disposables);
    }

  } else if (type === "pharma") {
    /* capsule plus a small molecule */
    A(THREE, g, new THREE.BoxGeometry(0.95*S, 0.14*S, 0.80*S), dark, -0.30*S, 0.07*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.40*S, 0.40*S, 0.95*S, 12), body, -0.35*S, 0.80*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.SphereGeometry(0.40*S, 12, 8), body, -0.35*S, 1.27*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.SphereGeometry(0.40*S, 12, 8), dark, -0.35*S, 0.33*S, 0, 0,0,0, disposables);
    var nodes = [[0.55,0.95,0],[0.95,1.28,0.16],[0.95,0.62,-0.16],[1.32,0.95,0]];
    for (var n2 = 0; n2 < nodes.length; n2++) {
      A(THREE, g, new THREE.SphereGeometry(0.15*S, 10, 8), body,
        nodes[n2][0]*S, nodes[n2][1]*S, nodes[n2][2]*S, 0,0,0, disposables);
    }
    A(THREE, g, new THREE.CylinderGeometry(0.035*S,0.035*S,0.52*S,6), dark, 0.75*S, 1.11*S, 0.08*S, 0,0,-0.9, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.035*S,0.035*S,0.52*S,6), dark, 0.75*S, 0.79*S,-0.08*S, 0,0, 0.9, disposables);
    A(THREE, g, new THREE.CylinderGeometry(0.035*S,0.035*S,0.52*S,6), dark, 1.14*S, 1.11*S, 0.08*S, 0,0, 0.9, disposables);

  } else if (type === "port") {
    /* quay with a gantry crane and a stack of containers */
    A(THREE, g, new THREE.BoxGeometry(1.7*S, 0.12*S, 1.15*S), dark, 0, 0.06*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.13*S, 1.35*S, 0.13*S), body, -0.55*S, 0.87*S, -0.45*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.13*S, 1.35*S, 0.13*S), body, -0.55*S, 0.87*S,  0.45*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.13*S, 1.35*S, 0.13*S), body,  0.30*S, 0.87*S, -0.45*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.13*S, 1.35*S, 0.13*S), body,  0.30*S, 0.87*S,  0.45*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(2.5*S, 0.14*S, 0.16*S), body, 0.15*S, 1.58*S, -0.45*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(2.5*S, 0.14*S, 0.16*S), body, 0.15*S, 1.58*S,  0.45*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.55*S, 0.26*S, 0.26*S), dark, 0.75*S, 0.33*S, 0.10*S, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(0.55*S, 0.26*S, 0.26*S), body, 0.75*S, 0.59*S, 0.10*S, 0,0,0, disposables);

  } else if (type === "policy") {
    /* plinth, colonnade in front, entablature, extruded triangular pediment */
    A(THREE, g, new THREE.BoxGeometry(1.85*S, 0.20*S, 1.25*S), dark, 0, 0.10*S, 0, 0,0,0, disposables);
    A(THREE, g, new THREE.BoxGeometry(1.35*S, 0.78*S, 0.80*S), dark, 0, 0.59*S, -0.20*S, 0,0,0, disposables);
    for (var c = 0; c < 5; c++) {
      A(THREE, g, new THREE.CylinderGeometry(0.085*S, 0.085*S, 0.80*S, 10), body,
        (-0.62 + c*0.31)*S, 0.60*S, 0.46*S, 0,0,0, disposables);
    }
    A(THREE, g, new THREE.BoxGeometry(1.70*S, 0.13*S, 1.15*S), body, 0, 1.07*S, 0, 0,0,0, disposables);
    /* CylinderGeometry with 3 segments gives a pyramid, not a prism, and lands
       flat-side-up. Extruding an explicit triangle is unambiguous. */
    var tri = new THREE.Shape();
    tri.moveTo(-0.88*S, 0); tri.lineTo(0.88*S, 0); tri.lineTo(0, 0.44*S); tri.lineTo(-0.88*S, 0);
    var pedG = new THREE.ExtrudeGeometry(tri, { depth: 1.15*S, bevelEnabled: false, steps: 1, curveSegments: 1 });
    pedG.translate(0, 0, -0.575*S);
    A(THREE, g, pedG, body, 0, 1.13*S, 0, 0,0,0, disposables);

  } else {
    A(THREE, g, new THREE.BoxGeometry(1.0*S, 0.7*S, 1.0*S), body, 0, 0.35*S, 0, 0,0,0, disposables);
  }
  return g;
}

/* Sites in the same industrial belt sit within a few tenths of a degree of each
   other. At globe scale their models merge into one blob, so any cluster gets
   fanned out around its centroid and its members staggered in height. */
function declusterAssets(assets, minSepDeg) {
  var out = assets.map(function (a) {
    var c = {}; for (var k in a) c[k] = a[k];
    c._lon = a.lon; c._lat = a.lat; c._lift = 0;
    return c;
  });
  var used = [];
  for (var i = 0; i < out.length; i++) {
    if (used.indexOf(i) >= 0) continue;
    var group = [i];
    for (var j = i + 1; j < out.length; j++) {
      if (used.indexOf(j) >= 0) continue;
      var dlon = (out[j].lon - out[i].lon) * Math.cos(out[i].lat * Math.PI / 180);
      var dlat = out[j].lat - out[i].lat;
      if (Math.sqrt(dlon * dlon + dlat * dlat) < minSepDeg) group.push(j);
    }
    if (group.length < 2) continue;
    var clon = 0, clat = 0;
    for (var q = 0; q < group.length; q++) { clon += out[group[q]].lon; clat += out[group[q]].lat; }
    clon /= group.length; clat /= group.length;
    var rad = minSepDeg * 0.52;
    for (var q2 = 0; q2 < group.length; q2++) {
      var th = (q2 / group.length) * Math.PI * 2 - Math.PI / 4;
      var m = out[group[q2]];
      m._lon = clon + Math.cos(th) * rad / Math.cos(clat * Math.PI / 180);
      m._lat = clat + Math.sin(th) * rad;
      m._lift = q2 * 0.95;                    // stagger so the caps never merge
      used.push(group[q2]);
    }
  }
  return out;
}

function buildAssetHolos(THREE, assets, R, disposables, cfg) {
  cfg = cfg || {};
  var group = new THREE.Group();
  var items = [];
  var UP = new THREE.Vector3(0, 1, 0);
  var S = (cfg.modelScale || 1) * R * 0.0072;   // base; the caller rescales per frame
  var placed = declusterAssets(assets, cfg.minSepDeg || 0.52);


  /* ---- BEACON SYSTEM ---------------------------------------------------
     icon + hairline beam + soft ground glow + hover-only pulse ring.
     Deliberately NOT a permanent radar ring: clustered sites (Oragadam and
     Sriperumbudur are ~20km apart) merged into one disc under the old
     footprint rings. Geometry is pooled, so more sites cost draw calls
     rather than unique GPU resources. */
  function beaconGeom(THREE, key, make){
    var c = beaconGeom._c || (beaconGeom._c = {});
    if(!c[key]) c[key] = make();
    return c[key];
  }
  /* Muted, print-like palette - hue AND glow strength carry status, so it
     survives greyscale and colour-blind viewing. No neon. */
  var STATUS_COL = { critical:0xb7503f, maintenance:0xb7503f,
    amber:0xc9a63a, construction:0xc9a63a, clear:0x6f9c7d,
    operational:0x6f9c7d, planned:0x8b80ad, unknown:0x77736b };
  function statusColour(st){
    var k = (st||"unknown").toLowerCase();
    return STATUS_COL[k] !== undefined ? STATUS_COL[k] : STATUS_COL.unknown;
  }
  function iconGeom(THREE, type, u){
    var t = (type||"").toLowerCase();
    if(t.indexOf("solar")>=0)   return beaconGeom(THREE,"i_solar",function(){return new THREE.OctahedronGeometry(u,0);});
    if(t.indexOf("wind")>=0)    return beaconGeom(THREE,"i_wind",function(){return new THREE.TorusGeometry(u*0.72,u*0.20,4,4);});
    if(t.indexOf("hydro")>=0)   return beaconGeom(THREE,"i_hydro",function(){return new THREE.ConeGeometry(u*0.95,u*1.25,4);});
    if(t.indexOf("nuclear")>=0) return beaconGeom(THREE,"i_nuke",function(){return new THREE.TetrahedronGeometry(u*1.15,0);});
    if(t.indexOf("grid")>=0||t.indexOf("substation")>=0||t.indexOf("steel")>=0)
                                return beaconGeom(THREE,"i_grid",function(){return new THREE.CylinderGeometry(u*0.85,u*0.85,u*0.42,6);});
    if(t.indexOf("batt")>=0||t.indexOf("auto")>=0)
                                return beaconGeom(THREE,"i_batt",function(){return new THREE.BoxGeometry(u*1.25,u*0.85,u*0.85);});
    if(t.indexOf("pharma")>=0)  return beaconGeom(THREE,"i_pharma",function(){return new THREE.DodecahedronGeometry(u*0.86,0);});
    return beaconGeom(THREE,"i_dot",function(){return new THREE.SphereGeometry(u*0.80,10,8);});
  }

  for (var i = 0; i < placed.length; i++) {
    var a = placed[i];
    var w = a.weight === undefined ? 0.5 : a.weight;

    var g = new THREE.Group();
    var p = toXYZ(a._lon, a._lat, R * 1.012);
    var dir = new THREE.Vector3(p[0], p[1], p[2]).normalize();
    g.position.set(p[0], p[1], p[2]);
    g.quaternion.setFromUnitVectors(UP, dir);

    /* ---- beacon ----------------------------------------------------- */
    var col   = (a.status !== undefined) ? statusColour(a.status)
                : (a.color !== undefined ? a.color : STATUS_COL.unknown);
    var u     = S * (0.16 + 0.10 * w);
    var beamH = S * (1.25 + 0.85 * w);
    /* The animation loop is a DIFFERENT scope and cannot see `S`. Capture
       every value it needs here and hang it on the item record. */
    var _ringBase = S * (0.70 + 0.34 * w);

    var glowM = new THREE.MeshBasicMaterial({ color: col, transparent: true,
      opacity: 0.16, side: THREE.DoubleSide, depthWrite: false });
    var glow = new THREE.Mesh(beaconGeom(THREE,"b_glow",function(){
      return new THREE.CircleGeometry(1,24); }), glowM);
    glow.scale.setScalar(S * (0.42 + 0.26 * w));
    glow.rotation.x = -Math.PI/2; glow.position.y = S*0.004;
    g.add(glow); disposables.push(glowM);

    /* hover pulse - idle opacity 0. Keeps the name `ring` because the loop
       already spins items[].ring; only its role changes. */
    var baseM = new THREE.MeshBasicMaterial({ color: col, transparent: true,
      opacity: 0.0, side: THREE.DoubleSide, depthWrite: false });
    var base = new THREE.Mesh(beaconGeom(THREE,"b_ring",function(){
      return new THREE.RingGeometry(0.80,1.0,32); }), baseM);
    base.scale.setScalar(_ringBase);
    base.rotation.x = -Math.PI/2; base.position.y = S*0.006;
    g.add(base); disposables.push(baseM);

    var model = new THREE.Group();
    var beamM = new THREE.MeshBasicMaterial({ color: col, transparent: true,
      opacity: 0.34, depthWrite: false, side: THREE.DoubleSide });
    var beam = new THREE.Mesh(beaconGeom(THREE,"b_beam",function(){
      return new THREE.CylinderGeometry(1,1,1,6,1,true); }), beamM);
    beam.scale.set(S*0.020, beamH, S*0.020);
    beam.position.y = beamH/2;
    model.add(beam); disposables.push(beamM);

    var iconG = iconGeom(THREE, a.type || a.sector, u);
    var iconM = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.94 });
    var icon = new THREE.Mesh(iconG, iconM);
    icon.position.y = beamH + u*1.15;
    model.add(icon); disposables.push(iconM);

    /* larger, fainter shell reads as emission without a bloom pass */
    var haloM = new THREE.MeshBasicMaterial({ color: col, transparent: true,
      opacity: 0.20, depthWrite: false });
    var halo = new THREE.Mesh(iconG, haloM);
    halo.position.y = icon.position.y; halo.scale.setScalar(1.75);
    model.add(halo); disposables.push(haloM);

    var lift = a._lift * S;
    model.position.y = lift;
    model.traverse(function (o) { if (o.isMesh) o.userData = { kind:"asset", id:a.id }; });
    /* traverse overwrote userData on child meshes; the group's own is intact */
    model.userData.icon = icon; model.userData.beam = beam; model.userData.halo = halo;
    g.add(model);

    var mats = [baseM, glowM];
    model.traverse(function (o) { if (o.isMesh && mats.indexOf(o.material) < 0) mats.push(o.material); });

    g.visible = false;
    group.add(g);
    items.push({
      id: a.id, sector: a.sector, state: a.state, group: g,
      ring: base, node: model, beam: model, base: base, model: model,
      mats: mats, dir: dir, _ringBase: _ringBase,
      top: new THREE.Vector3(0, lift + 2.0 * S, 0).applyQuaternion(g.quaternion).add(g.position),
      lon: a._lon, lat: a._lat, data: a
    });
  }
  return { group: group, items: items };
}

/* A site sits on a sphere and the camera always looks at the sphere's centre,
   so a model directly under the view axis is seen from straight above: a
   furnace becomes a circle and a chimney becomes a dot. Leaning each model
   toward the viewer restores the silhouette without detaching it from its
   footprint — the base stays put, the structure tilts. */
function faceCamera(built, camera, tiltDeg) {
  if (!built.holos || !built.holos.length) return;
  if (built.assetStyle !== "model") return;   // pins stand along the normal
  var th = (tiltDeg === undefined ? 34 : tiltDeg) * Math.PI / 180;
  var sinT = Math.sin(th), cosT = Math.cos(th);
  var UP = new THREE.Vector3(0, 1, 0);
  var camL = new THREE.Vector3(), upL = new THREE.Vector3(), tgt = new THREE.Vector3();

  for (var i = 0; i < built.holos.length; i++) {
    var ho = built.holos[i];
    if (!ho.group.visible) continue;
    ho.group.updateMatrixWorld();
    camL.copy(camera.position);
    ho.group.worldToLocal(camL);
    var dx = camL.x, dz = camL.z;
    var len = Math.sqrt(dx * dx + dz * dz);
    if (len < 1e-4) {
      /* dead overhead: lean toward screen-down so it stands up in frame */
      upL.copy(camera.position).addScaledVector(camera.up, 40);
      ho.group.worldToLocal(upL);
      dx = upL.x - camL.x; dz = upL.z - camL.z;
      len = Math.sqrt(dx * dx + dz * dz) || 1;
    }
    tgt.set(dx / len * sinT, cosT, dz / len * sinT);
    ho.model.quaternion.setFromUnitVectors(UP, tgt);
  }
}

/* Exact horizon test for a point outside a sphere of radius R seen from C:
   the terminator is the plane X.C = R^2, so X.C > R^2 means visible. Returned
   as a smooth 0..1 ramp so arcs dissolve at the limb instead of being cut off. */
function horizonFade(px, py, pz, cam, R) {
  var d = (px * cam.x + py * cam.y + pz * cam.z) / (R * R);
  var k = (d - 1.0) / 0.16;
  return k < 0 ? 0 : (k > 1 ? 1 : k * k * (3 - 2 * k));
}

/* Advance the comet trails. t is seconds. */
function updateArcTrails(built, t, speed) {
  if (!built.arcs) return;
  speed = speed || 0.19;
  for (var k = 0; k < built.arcs.length; k++) {
    var arc = built.arcs[k];
    var head = (t * speed + arc.phase) % 1;
    var pos = arc.trail.geometry.attributes.position;
    var col = arc.trail.geometry.attributes.color;
    var span = 0.30;                       // how much of the arc the tail covers
    for (var i = 0; i < arc.n; i++) {
      var f = i / (arc.n - 1);
      var u = head - f * span;
      if (u < 0) u = 0;
      var p = arc.curve.getPoint(u);
      pos.setXYZ(i, p.x, p.y, p.z);
      /* squared falloff, and killed entirely once the tail runs past the start
         so it does not bunch into a bright blob at the origin */
      var k2 = (1 - f) * (1 - f) * (head - f * span < 0 ? 0.15 : 1);
      col.setXYZ(i, arc.base.r * k2, arc.base.g * k2, arc.base.b * k2);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    arc.dot.position.copy(arc.curve.getPoint(head));
  }
}

/* ------------------------------------------------------------------ build */
function buildSeraphGlobe(THREE, DATA, cfg) {
  cfg = cfg || {};
  var R = cfg.R || 100;
  var C = cfg.colors || {};
  var root = new THREE.Group();
  var disposables = [];
  var out = { root: root, R: R, assetStyle: (cfg.assetStyle || 'pin'), hot: [], anchors: [], arcs: [], fades: [],
              disposables: disposables, stats: {} };
  function registerFade(mat, rings) {
    var d = ringsDirection(rings);
    out.fades.push({ mat: mat, base: mat.opacity, dir: new THREE.Vector3(d[0], d[1], d[2]) });
  }

  /* ocean */
  var oceanGeo = new THREE.SphereGeometry(R, 72, 48);
  var oceanMat = new THREE.MeshPhongMaterial({
    color: C.ocean || 0x0a1420, emissive: C.oceanEmissive || 0x050a12,
    /* Specular was 0x113044 (blue) at shininess 18. Shininess that low gives an
       enormous highlight lobe, so the ocean grew a huge blue glare wherever the
       sun reflected. It survived the charcoal re-theme because specular was
       hard-coded here rather than exposed through cfg.colors. */
    shininess: C.oceanShininess === undefined ? 85 : C.oceanShininess,
    specular: C.oceanSpecular === undefined ? 0x0d0f12 : C.oceanSpecular
  });
  root.add(new THREE.Mesh(oceanGeo, oceanMat));
  disposables.push(oceanGeo, oceanMat);

  /* atmosphere rim */
  var atmGeo = new THREE.SphereGeometry(R * 1.055, 48, 32);
  var atmMat = new THREE.MeshBasicMaterial({
    color: C.atmosphere || 0x1c4f6b, transparent: true, opacity: 0.14,
    side: THREE.BackSide, depthWrite: false
  });
  root.add(new THREE.Mesh(atmGeo, atmMat));
  disposables.push(atmGeo, atmMat);

  /* starfield */
  if (cfg.stars !== false) {
    var N = cfg.starCount || 2600, sp = new Float32Array(N * 3), ss = new Float32Array(N);
    for (var si = 0; si < N; si++) {
      var u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2;
      var sr = R * (14 + Math.random() * 8), rp = Math.sqrt(1 - u * u);
      sp[si * 3] = sr * rp * Math.cos(th);
      sp[si * 3 + 1] = sr * u;
      sp[si * 3 + 2] = sr * rp * Math.sin(th);
      ss[si] = Math.random();
    }
    var sg = new THREE.BufferGeometry();
    sg.setAttribute("position", new THREE.BufferAttribute(sp, 3));
    var sm = new THREE.PointsMaterial({
      color: 0xffffff, size: R * 0.055, sizeAttenuation: true,
      transparent: true, opacity: 0.75, depthWrite: false
    });
    var stars = new THREE.Points(sg, sm);
    root.add(stars);
    disposables.push(sg, sm);
    out.stars = stars;
  }

  /* graticule */
  var gr = [];
  for (var lat = -75; lat <= 75; lat += 15) {
    var ring = [];
    for (var lo = -180; lo <= 180; lo += 5) ring.push([lo, lat]);
    gr.push(ring);
  }
  for (var lon = -180; lon < 180; lon += 15) {
    var mer = [];
    for (var la = -90; la <= 90; la += 5) mer.push([lon, la]);
    gr.push(mer);
  }
  var grGeo = ringsToLines(THREE, gr, R * 1.0005, 5);
  var grMat = new THREE.LineBasicMaterial({
    color: C.graticule || 0x1d3346, transparent: true, opacity: 0.5
  });
  root.add(new THREE.LineSegments(grGeo, grMat));
  disposables.push(grGeo, grMat);

  /* land fill */
  var landTris = [], allRings = [];
  for (var i = 0; i < DATA.world.length; i++) {
    var f = DATA.world[i];
    for (var r = 0; r < f.r.length; r++) {
      allRings.push(f.r[r]);
      landTris = landTris.concat(triangulate(THREE, f.r[r], 6));
    }
  }
  out.stats.landTris = landTris.length;
  var landGeo = trisToGeometry(THREE, landTris, R * 1.004);
  var landMat = new THREE.MeshPhongMaterial({
    color: C.land || 0x24384c, emissive: C.landEmissive || 0x0b1521,
    shininess: 2, specular: C.landSpecular === undefined ? 0x000000 : C.landSpecular
  });
  root.add(new THREE.Mesh(landGeo, landMat));
  disposables.push(landGeo, landMat);

  /* coastlines */
  var coastGeo = ringsToLines(THREE, allRings, R * 1.007, 2.5);
  var coastMat = new THREE.LineBasicMaterial({
    color: C.coast || 0x4d7896, transparent: true, opacity: 0.65
  });
  root.add(new THREE.LineSegments(coastGeo, coastMat));
  disposables.push(coastGeo, coastMat);

  /* trigger countries */
  var byName = {};
  for (var i2 = 0; i2 < DATA.world.length; i2++) byName[DATA.world[i2].n] = DATA.world[i2];
  var triggerGroups = cfg.triggers || [];
  for (var t = 0; t < triggerGroups.length; t++) {
    var tg = triggerGroups[t];

    /* tg.rings is a pre-dissolved boundary ({o,h} records). Falling back to
       per-country fills stacks 20+ overlapping polygons with internal seams,
       which is what made the EU read as a blur rather than a region. */
    var recs = tg.rings;
    if (!recs) {
      recs = [];
      for (var m = 0; m < tg.members.length; m++) {
        var cf = byName[tg.members[m]];
        if (cf) for (var rr = 0; rr < cf.r.length; rr++) recs.push(cf.r[rr]);
      }
    }
    if (!recs.length) continue;

    var tris = [], outerRings = [];
    for (var q = 0; q < recs.length; q++) {
      tris = tris.concat(triangulateWithHoles(THREE, recs[q], 5));
      outerRings.push(recs[q].o || recs[q]);
      var hh = recs[q].h || [];
      for (var z = 0; z < hh.length; z++) outerRings.push(hh[z]);
    }
    if (!tris.length) continue;

    var g = trisToGeometry(THREE, tris, R * 1.009);
    var mat = new THREE.MeshPhongMaterial({
      color: tg.color, emissive: tg.color, emissiveIntensity: tg.emissive === undefined ? 0.18 : tg.emissive,
      shininess: 6, transparent: true, opacity: tg.opacity === undefined ? 0.70 : tg.opacity
    });
    registerFade(mat, outerRings);
    var mesh = new THREE.Mesh(g, mat);
    mesh.userData = { kind: "trigger", id: tg.id, baseEmissive: mat.emissiveIntensity };
    root.add(mesh);
    disposables.push(g, mat);
    out.hot.push(mesh);

    /* crisp boundary — without this the fill has no defined edge */
    if (tg.edge) {
      /* Stroke a generalised boundary when one is supplied. Tracing the full
         fill outline at global zoom produces a haze, not an edge. */
      var strokeRings = outerRings;
      if (tg.edgeRings) {
        strokeRings = [];
        for (var e2 = 0; e2 < tg.edgeRings.length; e2++) {
          strokeRings.push(tg.edgeRings[e2].o || tg.edgeRings[e2]);
          var eh = tg.edgeRings[e2].h || [];
          for (var e3 = 0; e3 < eh.length; e3++) strokeRings.push(eh[e3]);
        }
      }
      var tEdgeGeo = ringsToLines(THREE, strokeRings, R * 1.0102, 3.0);
      var tEdgeMat = new THREE.LineBasicMaterial({
        color: tg.edge, transparent: true, opacity: 0.8
      });
      registerFade(tEdgeMat, outerRings);
      root.add(new THREE.LineSegments(tEdgeGeo, tEdgeMat));
      disposables.push(tEdgeGeo, tEdgeMat);
    }
  }

  /* india state outlines */
  var stRings = [];
  for (var s = 0; s < DATA.india.length; s++)
    for (var q = 0; q < DATA.india[s].r.length; q++) stRings.push(DATA.india[s].r[q].o);
  var stGeo = ringsToLines(THREE, stRings, R * 1.013, 1.2);
  var stMat = new THREE.LineBasicMaterial({
    color: C.stateLine || 0x63c7e8, transparent: true, opacity: 0.55
  });
  registerFade(stMat, stRings);
  var stateLines = new THREE.LineSegments(stGeo, stMat);
  root.add(stateLines);
  disposables.push(stGeo, stMat);
  out.stateLines = stateLines;

  /* stressed states — FLAT surface fills, same shell thickness as the country
     trigger fills above. No extrusion: these sit on the globe exactly the way
     the US and EU highlights do. */
  var stress = cfg.stress || {};
  var R_STATE_FILL = R * 1.0105;      // trigger fills sit at R*1.009
  for (var s2 = 0; s2 < DATA.india.length; s2++) {
    var st = DATA.india[s2];
    var info = stress[st.n];
    if (!info) continue;

    var tris2 = [];
    for (var rq = 0; rq < st.r.length; rq++)
      tris2 = tris2.concat(triangulate(THREE, st.r[rq].o, 1.5));
    var geo = trisToGeometry(THREE, tris2, R_STATE_FILL);
    var mat2 = new THREE.MeshPhongMaterial({
      color: cfg.hotColor || 0xf59e0b, emissive: cfg.hotColor || 0xf59e0b,
      emissiveIntensity: 0.30, shininess: 10, transparent: true, opacity: 0.78
    });
    registerFade(mat2, [st.r[0].o]);
    var mesh2 = new THREE.Mesh(geo, mat2);
    mesh2.userData = { kind: "state", id: st.n, baseEmissive: mat2.emissiveIntensity };
    root.add(mesh2);
    disposables.push(geo, mat2);
    out.hot.push(mesh2);

    /* bright edge so the region reads against the teal India fill */
    var edgeGeo = ringsToLines(THREE, [st.r[0].o], R * 1.0118, 1.2);
    var edgeMat = new THREE.LineBasicMaterial({
      color: cfg.hotEdge || 0xfde68a, transparent: true, opacity: 0.9
    });
    registerFade(edgeMat, [st.r[0].o]);
    root.add(new THREE.LineSegments(edgeGeo, edgeMat));
    disposables.push(edgeGeo, edgeMat);

    var cen = ringCentroid(st.r[0].o);
    var ap = toXYZ(cen[0], cen[1], R * 1.022);
    out.anchors.push({ id: st.n, pos: new THREE.Vector3(ap[0], ap[1], ap[2]), ratio: info.ratio });
  }

  /* origin -> india arcs.
     The travelling pulse is a comet TRAIL, not a dot riding a solid line: a
     48-vertex polyline whose head sits at the current parameter and whose tail
     fades behind it. LineBasicMaterial has no per-vertex alpha in r128, so the
     fade is done with vertex COLOURS ramping to black under AdditiveBlending —
     additive black is invisible, which gives a true fade without a shader. */
  var arcs = cfg.arcs || [];
  var TRAIL_N = cfg.trailPoints || 48;
  for (var a2 = 0; a2 < arcs.length; a2++) {
    var arc = arcs[a2];
    var p0 = toXYZ(arc.from[0], arc.from[1], R * 1.01);
    var p1 = toXYZ(arc.to[0], arc.to[1], R * 1.01);
    var v0 = new THREE.Vector3(p0[0], p0[1], p0[2]);
    var v1 = new THREE.Vector3(p1[0], p1[1], p1[2]);
    var ang = v0.angleTo(v1);
    var mid = v0.clone().add(v1).normalize().multiplyScalar(R * (1 + 0.30 * ang));
    var curve = new THREE.QuadraticBezierCurve3(v0, mid, v1);

    /* faint guide showing the whole path */
    var gpts = curve.getPoints(72);
    var cg = new THREE.BufferGeometry().setFromPoints(gpts);
    var gcol = new Float32Array(gpts.length * 3);
    cg.setAttribute("color", new THREE.BufferAttribute(gcol, 3));
    var cm = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true,
      opacity: cfg.guideOpacity === undefined ? 0.55 : cfg.guideOpacity
    });
    var line = new THREE.Line(cg, cm);
    root.add(line);
    disposables.push(cg, cm);

    /* comet trail */
    var tpos = new Float32Array(TRAIL_N * 3);
    var tcol = new Float32Array(TRAIL_N * 3);
    var tg = new THREE.BufferGeometry();
    tg.setAttribute("position", new THREE.BufferAttribute(tpos, 3));
    tg.setAttribute("color", new THREE.BufferAttribute(tcol, 3));
    var tm = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 1,
      blending: THREE.AdditiveBlending, depthWrite: false
    });
    var trail = new THREE.Line(tg, tm);
    trail.frustumCulled = false;
    root.add(trail);
    disposables.push(tg, tm);

    var dg = new THREE.SphereGeometry(R * 0.0095, 10, 8);
    var dm = new THREE.MeshBasicMaterial({
      color: arc.color, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false
    });
    var dot = new THREE.Mesh(dg, dm);
    root.add(dot);
    disposables.push(dg, dm);

    out.arcs.push({
      line: line, trail: trail, dot: dot, curve: curve, id: arc.id,
      phase: a2 * 0.37, base: new THREE.Color(arc.color), n: TRAIL_N,
      guideN: gpts.length
    });
  }

  /* physical asset holograms (steel plants, solar parks, auto plants, pharma) */
  if (cfg.assets && cfg.assets.length) {
    var holos = buildAssetHolos(THREE, cfg.assets, R, disposables, cfg.assetOpts);
    root.add(holos.group);
    out.holos = holos.items;
    out.holoGroup = holos.group;
  } else {
    out.holos = [];
  }

  /* cloud shell — a translucent sphere carrying an fBm field, drifting west
     to east. Purely atmospheric: see out.clouds if you want to swap in a real
     satellite composite instead. */
  if (cfg.clouds !== false) {
    var cw = cfg.cloudW || 1024, ch = cfg.cloudH || 512;
    var cdata = makeCloudData(cw, ch, cfg.cloudSeed || 7, cfg.cloudCover);
    var ctex = new THREE.DataTexture(cdata, cw, ch, THREE.RGBAFormat);
    ctex.wrapS = THREE.RepeatWrapping;
    ctex.minFilter = THREE.LinearFilter;
    ctex.magFilter = THREE.LinearFilter;
    ctex.needsUpdate = true;
    var cgeo = new THREE.SphereGeometry(R * 1.022, 64, 40);
    var cmat = new THREE.MeshPhongMaterial({
      map: ctex, transparent: true, opacity: cfg.cloudOpacity === undefined ? 0.42 : cfg.cloudOpacity,
      depthWrite: false, shininess: 0, emissive: 0x0a0a0c
    });
    var cmesh = new THREE.Mesh(cgeo, cmat);
    root.add(cmesh);
    disposables.push(cgeo, cmat, ctex);
    out.clouds = cmesh;
    out.cloudTexture = ctex;
  }

  return out;
}

/* Dim any highlight whose region has swung towards the limb. A fill viewed at
   a grazing angle foreshortens into an unreadable smear that reads as a glow
   rather than as geography.

   The cutoff has to be measured against the HORIZON, not a fixed angle: the
   visible hemisphere is bounded by cos(theta) = R / cameraDistance, which is
   65 deg when zoomed in on India and 73 deg pulled back to the global view.
   A fixed threshold that looks right at one distance is wrong at the other. */
function applyLimbFade(built, cameraPosition) {
  if (!built.fades || !built.fades.length) return;
  var cx = cameraPosition.x, cy = cameraPosition.y, cz = cameraPosition.z;
  var dist = Math.sqrt(cx * cx + cy * cy + cz * cz) || 1;
  cx /= dist; cy /= dist; cz /= dist;

  var horizon = (built.R || 100) / dist;              // cos of the horizon angle
  var fadeOut = Math.min(0.90, horizon + 0.12);       // gone by here
  var fadeIn  = Math.min(0.96, horizon + 0.30);       // full strength by here

  for (var i = 0; i < built.fades.length; i++) {
    var f = built.fades[i];
    var d = cx * f.dir.x + cy * f.dir.y + cz * f.dir.z;
    var k = (d - fadeOut) / (fadeIn - fadeOut);
    k = k < 0 ? 0 : (k > 1 ? 1 : k * k * (3 - 2 * k));
    f.mat.opacity = f.base * k;
  }
}

root.SERAPH_GLOBE = {
  build: buildSeraphGlobe, toXYZ: toXYZ, horizonFade: horizonFade, faceCamera: faceCamera,
  siteModel: siteModel, matFor: matFor, makeCloudData: makeCloudData,
  applyLimbFade: applyLimbFade, updateArcTrails: updateArcTrails
};

})(typeof globalThis !== "undefined" ? globalThis : this);


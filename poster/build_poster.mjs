// Builds poster/poster.svg: "the world as seen from Julia's place".
//
// A fisheye azimuthal projection centred on Julia's apartment. Inside the
// lens (8 km) distances are true, so lower Manhattan / Brooklyn / Queens keep
// their real shape; beyond it the radius is compressed so the whole world
// wraps around New York.
//
//   npm install && node build_poster.mjs     (then ./render.sh for PDF + PNG)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  geoProjection, geoAzimuthalEquidistantRaw, geoPath, geoGraticule, geoDistance, geoCircle,
} from "d3-geo";
import { feature, mesh } from "topojson-client";
import { prepGeo, rewindPolygon } from "./prep_geo.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const GEO = path.join(HERE, "geo");
const readJSON = (p) => JSON.parse(fs.readFileSync(p, "utf8"));

await prepGeo();
const data = readJSON(path.join(ROOT, "data", "memmap.json"));

// ---------------------------------------------------------------- palette
const C = {
  paper: "#FBF5EA", ink: "#2A2420", muted: "#6B5F55", tomato: "#E4572E",
  sun: "#F2B630", water: "#C9DFEA", deep: "#2D5D7B", land: "#EFE6D2",
  line: "#D9CCB0", park: "#BFD6A8", pink: "#F4A6B8",
};
const F = {
  display: "'Fraunces', Georgia, serif",
  body: "'DM Sans', 'Helvetica Neue', Arial, sans-serif",
  hand: "'Caveat', 'Bradley Hand', cursive",
};

// ---------------------------------------------------------------- layout (1 unit = 0.01 in; 18 x 24 in)
const W = 1800, H = 2400;
const CX = 900, CY = 1122, R = 760;   // world circle
const RL = 0.44 * R;                  // lens radius on paper
const EARTH_KM = 6371;
const DL = 7.2;                         // lens radius on the ground, km
const DMAX = Math.PI * EARTH_KM;      // antipode
const P = 0.42;                       // compression exponent outside the lens
const HOME = [-73.99989, 40.71889];

// Radial mapping: ground distance (km) -> paper radius (units)
function radius(dKm) {
  if (dKm <= DL) return RL * dKm / DL;
  const t = (dKm - DL) / (DMAX - DL);
  return RL + (R - RL) * Math.pow(t, P);
}

// Raw projection in radians, already rotated so HOME is at (0,0).
function fisheyeRaw(lambda, phi) {
  const [x, y] = geoAzimuthalEquidistantRaw(lambda, phi); // |(x,y)| = angular distance c
  const c = Math.hypot(x, y);
  if (c < 1e-12) return [0, 0];
  const k = radius(c * EARTH_KM) / c;
  return [x * k, y * k];
}

const projection = geoProjection(fisheyeRaw)
  .rotate([-HOME[0], -HOME[1]])
  .scale(1)
  .translate([CX, CY])
  .clipAngle(179.2)
  .precision(0.05);
const pathGen = geoPath(projection);

// Inside the lens we use the identical projection but clip tightly, so the detailed layers stop at the rim.
const lensProjection = geoProjection(fisheyeRaw)
  .rotate([-HOME[0], -HOME[1]])
  .scale(1)
  .translate([CX, CY])
  .clipAngle((DL * 1.02 / EARTH_KM) * 180 / Math.PI)
  .precision(0.01);
const lensPath = geoPath(lensProjection);

const fmt = (n) => (Math.round(n * 10) / 10).toString();
// Thin a d3 path string in paper space: drop vertices closer than `tol` units to
// the last one kept, drop sub-paths smaller than `minSize`, round to 0.1 units.
// The fisheye squeezes most of the planet into a thin band, so this removes
// the bulk of the vertices without any visible change.
function d(p, tol = 0.45, minSize = 0.8) {
  if (!p) return "";
  const out = [];
  for (const sub of p.split(/(?=M)/)) {
    const closed = /Z\s*$/.test(sub);
    const nums = sub.replace(/Z/g, "").slice(1).split(/L/).map((s) => s.split(",").map(Number));
    const kept = [];
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nums.forEach(([x, y], i) => {
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      const last = kept[kept.length - 1];
      if (!last || i === nums.length - 1 || Math.hypot(x - last[0], y - last[1]) >= tol) kept.push([x, y]);
    });
    if (closed && (maxX - minX < minSize && maxY - minY < minSize)) continue;
    if (kept.length < (closed ? 3 : 2)) continue;
    out.push("M" + kept.map(([x, y]) => `${Math.round(x * 10) / 10},${Math.round(y * 10) / 10}`).join("L") + (closed ? "Z" : ""));
  }
  return out.join("");
}
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/'/g, "&#39;");

// ---------------------------------------------------------------- geo layers
const worldTopo = readJSON(path.join(HERE, "node_modules", "world-atlas", "countries-10m.json"));
const countries = feature(worldTopo, worldTopo.objects.countries);
// USA comes from the Census file. Some tiny 10m polygons (e.g. Maldives) come out inside-out; rewind them.
countries.features = countries.features.filter((f) => f.id !== "840").map((f) => ({
  ...f,
  geometry: f.geometry.type === "Polygon"
    ? { type: "Polygon", coordinates: rewindPolygon(f.geometry.coordinates) }
    : { type: "MultiPolygon", coordinates: f.geometry.coordinates.map(rewindPolygon) },
}));
const countryBorders = mesh(worldTopo, worldTopo.objects.countries, (a, b) => a !== b && a.id !== "840" && b.id !== "840");

const statesTopo = readJSON(path.join(GEO, "us-states-500k.topo.json"));
const states = feature(statesTopo, statesTopo.objects.states);
const stateBorders = mesh(statesTopo, statesTopo.objects.states, (a, b) => a !== b);
const nj = { type: "FeatureCollection", features: states.features.filter((f) => f.properties.abbr === "NJ") };

const lakes = readJSON(path.join(GEO, "lakes-50m.json"));
const borosTopo = readJSON(path.join(GEO, "nyc-boroughs.topo.json"));
const boros = feature(borosTopo, borosTopo.objects.b);
const osmTopo = readJSON(path.join(GEO, "nyc-osm.topo.json"));
const osm = feature(osmTopo, osmTopo.objects.osm);
const parks = osm.features.filter((f) => f.properties.k === "park");
const roads = osm.features.filter((f) => f.properties.k === "road");

const out = [];
const add = (s) => out.push(s);

// ---------------------------------------------------------------- svg head
add(`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 ${W} ${H}" width="18in" height="24in">`);
add(`<defs>
  <style>
    .t-display { font-family: ${F.display}; font-variation-settings: "SOFT" 100, "WONK" 0; }
    .t-body { font-family: ${F.body}; }
    .t-hand { font-family: ${F.hand}; }
    .halo { paint-order: stroke; stroke: ${C.paper}; stroke-linejoin: round; }
    .halo-w { paint-order: stroke; stroke: ${C.water}; stroke-linejoin: round; }
  </style>
  <clipPath id="world-clip"><circle cx="${CX}" cy="${CY}" r="${R}"/></clipPath>
  <clipPath id="lens-clip"><circle cx="${CX}" cy="${CY}" r="${RL}"/></clipPath>
  <radialGradient id="ocean-grad" cx="50%" cy="50%" r="50%">
    <stop offset="0%" stop-color="${C.water}"/>
    <stop offset="78%" stop-color="${C.water}"/>
    <stop offset="100%" stop-color="#B3CFDD"/>
  </radialGradient>
  <radialGradient id="lens-glint" cx="38%" cy="30%" r="75%">
    <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.22"/>
    <stop offset="45%" stop-color="#FFFFFF" stop-opacity="0"/>
  </radialGradient>
  <path id="rim-text-path" d="M ${CX - (RL + 13)} ${CY} a ${RL + 13} ${RL + 13} 0 1 1 ${2 * (RL + 13)} 0 a ${RL + 13} ${RL + 13} 0 1 1 ${-2 * (RL + 13)} 0"/>
  <path id="outer-text-path" d="M ${CX - (R + 26)} ${CY} a ${R + 26} ${R + 26} 0 1 1 ${2 * (R + 26)} 0 a ${R + 26} ${R + 26} 0 1 1 ${-2 * (R + 26)} 0"/>
</defs>`);

// paper
add(`<rect width="${W}" height="${H}" fill="${C.paper}"/>`);

// ---------------------------------------------------------------- world
add(`<g clip-path="url(#world-clip)">`);
add(`<circle cx="${CX}" cy="${CY}" r="${R}" fill="url(#ocean-grad)"/>`);
// graticule: faint, shows the fisheye warp
add(`<path d="${d(pathGen(geoGraticule().step([15, 15])()))}" fill="none" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="0.8"/>`);
add(`<path d="${d(pathGen(countries))}" fill="${C.land}" stroke="none"/>`);
add(`<path d="${d(pathGen(states))}" fill="${C.land}" stroke="none"/>`);
add(`<path d="${d(pathGen(lakes))}" fill="${C.water}" stroke="none"/>`);
add(`<path d="${d(pathGen(countryBorders))}" fill="none" stroke="${C.line}" stroke-width="0.9"/>`);
add(`<path d="${d(pathGen(stateBorders))}" fill="none" stroke="${C.line}" stroke-width="0.6"/>`);

// distance rings
const RINGS = [[100, "100 km"], [1000, "1,000 km"], [5000, "5,000 km"], [10000, "10,000 km"], [15000, "15,000 km"]];
for (const [km, label] of RINGS) {
  const r = radius(km);
  add(`<circle cx="${CX}" cy="${CY}" r="${fmt(r)}" fill="none" stroke="${C.deep}" stroke-opacity="0.35" stroke-width="1" stroke-dasharray="2 6" stroke-linecap="round"/>`);
  // label on the lower-right diagonal, in open water as much as possible
  const a = (128 * Math.PI) / 180;
  const x = CX + r * Math.cos(a), y = CY + r * Math.sin(a);
  add(`<text x="${fmt(x)}" y="${fmt(y + 4)}" text-anchor="middle" class="t-body halo" stroke-width="5" font-size="11" letter-spacing="1.2" fill="${C.deep}" fill-opacity="0.8">${label.toUpperCase()}</text>`);
}
add(`</g>`);
add(`<circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="${C.ink}" stroke-width="2.4"/>`);
add(`<circle cx="${CX}" cy="${CY}" r="${R + 9}" fill="none" stroke="${C.ink}" stroke-width="0.8"/>`);

// ---------------------------------------------------------------- lens (true-shape NYC)
add(`<g clip-path="url(#lens-clip)">`);
add(`<circle cx="${CX}" cy="${CY}" r="${RL}" fill="${C.water}"/>`);
add(`<path d="${d(lensPath(nj))}" fill="${C.land}" stroke="none"/>`);
add(`<path d="${d(lensPath({ type: "FeatureCollection", features: boros.features }))}" fill="${C.land}" stroke="${C.line}" stroke-width="0.8"/>`);
add(`<path d="${d(lensPath({ type: "FeatureCollection", features: parks }))}" fill="${C.park}" stroke="none"/>`);
for (const [rank, width, color] of [[4, 0.9, "#FFFFFF"], [3, 1.3, "#FFFFFF"], [2, 1.9, "#FFFFFF"], [1, 2.4, "#F7E7C4"]]) {
  const fc = { type: "FeatureCollection", features: roads.filter((f) => f.properties.r === rank) };
  add(`<path d="${d(lensPath(fc))}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" opacity="0.95"/>`);
}
add(`<circle cx="${CX}" cy="${CY}" r="${RL}" fill="url(#lens-glint)"/>`);
add(`</g>`);

// lens labels: boroughs + water
const lensLabel = (lng, lat, text, opts = {}) => {
  const [x, y] = projection([lng, lat]);
  const { size = 13, spacing = 4, color = C.muted, italic = false, rotate = 0, cls = "halo", sw = 4 } = opts;
  add(`<text x="${fmt(x)}" y="${fmt(y)}" transform="rotate(${rotate} ${fmt(x)} ${fmt(y)})" text-anchor="middle" class="t-body ${cls}" stroke-width="${sw}" font-size="${size}" letter-spacing="${spacing}" fill="${color}" ${italic ? 'font-style="italic"' : ""} font-weight="600">${esc(text)}</text>`);
};
lensLabel(-73.95, 40.68, "BROOKLYN", { size: 14, spacing: 6 });
lensLabel(-74.033, 40.765, "NEW JERSEY", { size: 12, spacing: 5 });

// lens rim: a little brass-free magnifying-glass ring with text
add(`<circle cx="${CX}" cy="${CY}" r="${RL + 13}" fill="none" stroke="${C.paper}" stroke-width="26"/>`);
add(`<circle cx="${CX}" cy="${CY}" r="${RL}" fill="none" stroke="${C.ink}" stroke-width="2"/>`);
add(`<circle cx="${CX}" cy="${CY}" r="${RL + 26}" fill="none" stroke="${C.ink}" stroke-width="1.2"/>`);
add(`<text class="t-body" font-size="11.5" font-weight="600" letter-spacing="4.6" fill="${C.ink}"><textPath href="#rim-text-path" startOffset="0" textLength="${fmt(2 * Math.PI * (RL + 13) - 2)}" lengthAdjust="spacing">${
  Array(5).fill("NEW YORK CITY · TRUE TO SCALE · ").join("")
}</textPath></text>`);

// ---------------------------------------------------------------- world labels
// Region names set along the circles, so the fisheye stays readable.
function ringLabel(lng, lat, text, { size = 13, spacing = 5, color = C.muted, italic = false, weight = 600 } = {}) {
  const [x, y] = projection([lng, lat]);
  let a = (Math.atan2(y - CY, x - CX) * 180) / Math.PI + 90;
  if (a > 90 && a < 270) a -= 180; // keep text upright
  add(`<text x="${fmt(x)}" y="${fmt(y)}" transform="rotate(${fmt(a)} ${fmt(x)} ${fmt(y)})" text-anchor="middle" dominant-baseline="middle" class="t-body" font-size="${size}" letter-spacing="${spacing}" font-weight="${weight}" fill="${color}" ${italic ? 'font-style="italic"' : ""}>${esc(text)}</text>`);
}
const WORLD_LABELS = [
  [-100, 57, "CANADA"], [-98, 39, "UNITED STATES"], [-102, 23, "MEXICO"], [-152, 64, "ALASKA"],
  [-42, 73, "GREENLAND"], [12, 49, "EUROPE"], [20, 6, "AFRICA"], [-60, -14, "SOUTH AMERICA"],
  [90, 63, "RUSSIA"], [78, 22, "INDIA"], [134, -25, "AUSTRALIA"],
];
for (const [lng, lat, t] of WORLD_LABELS) ringLabel(lng, lat, t);
for (const [lng, lat, t] of [[-150, 12, "Pacific Ocean"], [-38, 28, "Atlantic Ocean"], [-25, -30, "South Atlantic"], [80, -25, "Indian Ocean"]]) {
  ringLabel(lng, lat, t, { size: 16, spacing: 3, color: C.deep, italic: true, weight: 500 });
}
{
  const [x, y] = projection([0, 90]);
  add(`<g transform="translate(${fmt(x)} ${fmt(y)})"><path d="M0,-7 L1.8,-1.8 L7,0 L1.8,1.8 L0,7 L-1.8,1.8 L-7,0 L-1.8,-1.8Z" fill="${C.deep}"/></g>`);
  add(`<text x="${fmt(x + 10)}" y="${fmt(y + 4)}" class="t-hand" font-size="17" font-weight="600" fill="${C.deep}">north pole</text>`);
}

// ---------------------------------------------------------------- pins
// b: where the numbered badge sits (paper units; omit to sit on the point).
// A leader line joins the badge to the true location. side: label position.
const PLACE = {
  // downtown cluster -> a column of callouts over the Hudson / Jersey City
  sobs:        { b: [800, 1028], side: "left" },
  mimis:       { b: [800, 1078], side: "left" },
  spongies:    { b: [800, 1128], side: "left" },
  home:        { b: [806, 1190], side: "left" },
  bao:         { b: [805, 1268], side: "left" },
  wus:         { b: [815, 1318], side: "left" },
  msg:         { b: [850, 960], side: "left" },
  centralpark: { b: [975, 818], side: "left", short: "Central Park" },
  // east side -> callouts over the East River / Brooklyn / Queens
  pennclub:    { b: [1020, 918], side: "right" },
  recente:     { b: [1010, 1045], side: "right" },
  ludlow:      { b: [1010, 1100], side: "right" },
  sonic:       { b: [1170, 1035], side: "below" },
  mccarren:    { b: [1130, 1135], side: "below", short: "McCarren Park" },
  williamsburg:{ b: [1070, 1230], side: "below" },
  botanic:     { b: [985, 1400], side: "left" },
  // region
  oley:        { b: [492, 1238], side: "left" },
  beacon:      { b: [911, 710], side: "above" },
  hamptons:    { b: [1310, 1062], side: "right" },
  harvard:     { b: [1248, 848], side: "right" },
  // world
  vancouver:   { b: [436, 796], side: "above" },
  ginza:       { b: [402, 372], side: "left", short: "Seafood buffet, Ginza", group: "japan" },
  kiyomizu:    { b: [402, 418], side: "left", group: "japan" },
  shinsaibashi:{ b: [402, 464], side: "left", group: "japan" },
  usj:         { b: [402, 510], side: "left", group: "japan" },
  manila:      { b: [700, 332], side: "left" },
  chengdu:     { b: [1010, 336], side: "right" },
};

const peopleNames = (pl) => pl.people.map((p) => p.name).join(", ");
// Split long name lists over two lines at a comma, as evenly as possible.
function nameLines(pl) {
  const names = pl.people.map((p) => p.name);
  const all = names.join(", ");
  if (all.length <= 24) return [all];
  let best = null;
  for (let i = 1; i < names.length; i++) {
    const a = names.slice(0, i).join(", ") + ",", b = names.slice(i).join(", ");
    const score = Math.max(a.length, b.length);
    if (!best || score < best.score) best = { score, lines: [a, b] };
  }
  return best.lines;
}

function textBlock(x, y, side, title, subs, r) {
  const anchor = side === "left" ? "end" : side === "right" ? "start" : "middle";
  const gap = r + 6;
  const ox = side === "left" ? -gap : side === "right" ? gap : 0;
  const oy = side === "above" ? -(gap + 18 + 19 * (subs.length - 1)) : side === "below" ? gap + 14 : 0;
  const tx = x + ox, ty = y + oy;
  add(`<text x="${fmt(tx)}" y="${fmt(ty - 1)}" text-anchor="${anchor}" class="t-body halo" stroke-width="4.5" font-size="14" font-weight="700" fill="${C.ink}">${esc(title)}</text>`);
  subs.forEach((s, i) => {
    add(`<text x="${fmt(tx)}" y="${fmt(ty + 17 + i * 19)}" text-anchor="${anchor}" class="t-hand halo" stroke-width="4.5" font-size="20" font-weight="600" fill="${C.tomato}">${esc(s)}</text>`);
  });
}

const leaders = [], dots = [], badges = [], labels = [];
const groups = {};
for (const pl of data.places) {
  const [px, py] = projection([pl.lng, pl.lat]);
  const o = PLACE[pl.key] || { side: "right" };
  const [bx, by] = o.b || [px, py];
  const r = pl.key === "home" ? 16 : 12.5;
  if (o.group) {
    (groups[o.group] ||= []).push({ px, py, bx, by, r });
  } else if (Math.hypot(bx - px, by - py) > r) {
    leaders.push(`<line x1="${fmt(px)}" y1="${fmt(py)}" x2="${fmt(bx)}" y2="${fmt(by)}" stroke="${C.ink}" stroke-width="0.9" stroke-opacity="0.7"/>`);
  }
  dots.push(`<circle cx="${fmt(px)}" cy="${fmt(py)}" r="3.4" fill="${C.ink}" stroke="${C.paper}" stroke-width="1.3"/>`);
  badges.push(`<circle cx="${fmt(bx)}" cy="${fmt(by)}" r="${r}" fill="${C.tomato}" stroke="${C.paper}" stroke-width="2.4"/>`);
  badges.push(`<text x="${fmt(bx)}" y="${fmt(by + (pl.key === "home" ? 5.6 : 4.6))}" text-anchor="middle" class="t-body" font-size="${pl.key === "home" ? 16 : 13}" font-weight="700" fill="#FFFFFF">${pl.num}</text>`);
  labels.push([bx, by, o.side, o.short || pl.name, nameLines(pl), r]);
  if (pl.extra_pin) {
    const [ex, ey] = projection([pl.extra_pin.lng, pl.extra_pin.lat]);
    dots.push(`<circle cx="${fmt(ex)}" cy="${fmt(ey)}" r="4.6" fill="${C.sun}" stroke="${C.ink}" stroke-width="1"/>`);
    labels.push(() => add(`<text x="${fmt(ex - 6)}" y="${fmt(ey + 22)}" text-anchor="end" class="t-hand halo" stroke-width="4" font-size="16" font-weight="600" fill="${C.ink}">Oberon</text>`));
  }
}
// Grouped callouts (Japan): ring the cluster, one leader to a bracket, ticks to each badge.
for (const members of Object.values(groups)) {
  const gx = members.reduce((a, m) => a + m.px, 0) / members.length;
  const gy = members.reduce((a, m) => a + m.py, 0) / members.length;
  const ringR = Math.max(...members.map((m) => Math.hypot(m.px - gx, m.py - gy))) + 10;
  const brX = members[0].bx + members[0].r + 14;
  const ys = members.map((m) => m.by);
  const top = Math.min(...ys), bot = Math.max(...ys), mid = (top + bot) / 2;
  leaders.push(`<circle cx="${fmt(gx)}" cy="${fmt(gy)}" r="${fmt(ringR)}" fill="none" stroke="${C.ink}" stroke-width="1" stroke-dasharray="3 3"/>`);
  const ang = Math.atan2(mid - gy, brX - gx);
  leaders.push(`<path d="M${fmt(gx + ringR * Math.cos(ang))},${fmt(gy + ringR * Math.sin(ang))} L${fmt(brX)},${fmt(mid)} M${fmt(brX)},${fmt(top)} L${fmt(brX)},${fmt(bot)} ${members.map((m) => `M${fmt(m.bx + m.r)},${fmt(m.by)} L${fmt(brX)},${fmt(m.by)}`).join(" ")}" fill="none" stroke="${C.ink}" stroke-width="1" stroke-opacity="0.75"/>`);
  leaders.push(`<text x="${fmt(gx + ringR * 0.75)}" y="${fmt(gy - ringR - 6)}" class="t-hand halo" stroke-width="4" font-size="24" font-weight="700" fill="${C.deep}">Japan</text>`);
}
add(`<g id="leaders">${leaders.join("")}</g>`);
add(`<g id="dots">${dots.join("")}</g>`);
add(`<g id="labels">`);
for (const l of labels) typeof l === "function" ? l() : textBlock(...l);
add(`</g>`);
add(`<g id="badges">${badges.join("")}</g>`);

// ---------------------------------------------------------------- title block
add(`<text x="${CX}" y="196" text-anchor="middle" class="t-display" font-size="150" font-weight="560" letter-spacing="-2" fill="${C.ink}">Julia at <tspan fill="${C.tomato}" font-style="italic">24</tspan></text>`);
add(`<text x="${CX}" y="258" text-anchor="middle" class="t-display" font-size="30" font-style="italic" font-weight="400" fill="${C.muted}">${esc(data.subtitle)}</text>`);
add(`<text x="${CX - 640}" y="110" text-anchor="middle" transform="rotate(-8 ${CX - 640} 110)" class="t-hand" font-size="46" font-weight="700" fill="${C.tomato}">happy 25th!</text>`);
add(`<text x="${CX + 640}" y="108" text-anchor="middle" transform="rotate(7 ${CX + 640} 108)" class="t-hand" font-size="40" font-weight="600" fill="${C.deep}">33 notes · 26 places</text>`);

// a note set along the southern ocean
{
  const r = 0.5 * (radius(1000) + radius(5000)) + 6;
  add(`<path id="south-arc" d="M ${fmt(CX - r)} ${CY} A ${fmt(r)} ${fmt(r)} 0 0 0 ${fmt(CX + r)} ${CY}" fill="none"/>`);
  add(`<text class="t-hand halo-w" stroke-width="5" font-size="36" font-weight="600" fill="${C.deep}"><textPath href="#south-arc" startOffset="50%" text-anchor="middle">every pin is a person who loves you</textPath></text>`);
}

// corner notes
const note = (x, y, rot, lines, color = C.deep, size = 28) => lines.forEach((t, i) =>
  add(`<text x="${x}" y="${y + i * size * 1.05}" text-anchor="middle" transform="rotate(${rot} ${x} ${y})" class="t-hand" font-size="${size}" font-weight="600" fill="${color}">${esc(t)}</text>`));
note(250, 1760, -5, ["the whole world,", "as seen from home"]);
note(1555, 1748, 4, ["inside the ring: true to scale.", "outside: the farther from home,", "the more it squeezes"], C.muted, 22);

// ---------------------------------------------------------------- key
const KEY_TOP = 1960;
add(`<text x="110" y="${KEY_TOP - 32}" class="t-body" font-size="12" font-weight="700" letter-spacing="2.5" fill="${C.ink}">THE DIRECTORY <tspan font-weight="400" fill="${C.muted}" letter-spacing="1.2">· NUMBERS MATCH THE PINS ABOVE AND THE NOTES IN THE PAMPHLET</tspan></text>`);
add(`<line x1="110" y1="${KEY_TOP - 22}" x2="${W - 110}" y2="${KEY_TOP - 22}" stroke="${C.ink}" stroke-width="1"/>`);
const cols = 4, colW = (W - 220) / cols, rows = Math.ceil(data.places.length / cols), rowH = 51;
data.places.forEach((pl, i) => {
  const col = Math.floor(i / rows), row = i % rows;
  const x = 110 + col * colW, y = KEY_TOP + 14 + row * rowH;
  add(`<circle cx="${x + 12}" cy="${y}" r="11" fill="${C.tomato}"/>`);
  add(`<text x="${x + 12}" y="${y + 4.3}" text-anchor="middle" class="t-body" font-size="12" font-weight="700" fill="#FFFFFF">${pl.num}</text>`);
  add(`<text x="${x + 31}" y="${y + 4.5}" class="t-body" font-size="13.5" font-weight="700" fill="${C.ink}">${esc(pl.name)} <tspan font-weight="400" fill="${C.muted}" font-size="11.5">${esc(pl.area)}</tspan></text>`);
  add(`<text x="${x + 31}" y="${y + 25}" class="t-hand" font-size="19" font-weight="600" fill="${C.tomato}">${esc(peopleNames(pl))}</text>`);
});
add(`<text x="${CX}" y="${H - 52}" text-anchor="middle" class="t-body" font-size="11" letter-spacing="1.5" fill="${C.muted}">MADE WITH LOVE BY PJ, FAMILY &amp; FRIENDS · OCTOBER 2026 · MAP DATA © OPENSTREETMAP CONTRIBUTORS, NATURAL EARTH, US CENSUS BUREAU, NYC OPEN DATA</text>`);

add(`</svg>`);
fs.writeFileSync(path.join(HERE, "poster.svg"), out.join("\n"));
console.log("wrote poster/poster.svg", (fs.statSync(path.join(HERE, "poster.svg")).size / 1024).toFixed(0), "KB");

// poster.html inlines the SVG so web fonts and textPath render when printing.
const FONTS = "https://fonts.googleapis.com/css2?family=Caveat:wght@400..700&family=DM+Sans:ital,opsz,wght@0,9..40,300..800;1,9..40,300..800&family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,300..800,0..100,0..1;1,9..144,300..800,0..100,0..1&display=block";
fs.writeFileSync(path.join(HERE, "poster.html"), `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Julia at 24 · poster</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">
<style>
  @page { size: 18in 24in; margin: 0; }
  html, body { margin: 0; padding: 0; background: ${C.paper}; }
  svg { display: block; width: 18in; height: 24in; }
  @media screen { svg { width: 100vw; height: auto; } }
</style></head>
<body>
${out.join("\n")}
</body></html>
`);
console.log("wrote poster/poster.html");

// Downloads (once) and compacts the geo data the poster needs into poster/geo/.
// Raw downloads land in poster/geo/raw/ (git-ignored); the compact files are committed.
//
//   node prep_geo.mjs          build any missing compact files
//   node prep_geo.mjs --force  rebuild them all
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import * as shapefile from "shapefile";
import { geoArea } from "d3-geo";
import { topology } from "topojson-server";
import { presimplify, simplify } from "topojson-simplify";
import { quantize } from "topojson-client";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GEO = path.join(HERE, "geo");
const RAW = path.join(GEO, "raw");
fs.mkdirSync(RAW, { recursive: true });
const FORCE = process.argv.includes("--force");

// Lens bbox around Julia's place (~8 km radius plus margin).
export const LENS_BBOX = { s: 40.64, w: -74.1, n: 40.798, e: -73.898 };

const SOURCES = {
  states: "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip",
  boroughs: "https://data.cityofnewyork.us/api/geospatial/gthc-hcne?method=export&format=GeoJSON",
  lakes: "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson",
  overpass: "https://overpass-api.de/api/interpreter",
};

async function download(url, dest, init) {
  if (fs.existsSync(dest)) return dest;
  console.log("downloading", url);
  const res = await fetch(url, { headers: { "User-Agent": "memmap-poster/1.0 (personal birthday gift)" }, ...init });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  fs.writeFileSync(dest, Buffer.from(await res.arrayBuffer()));
  return dest;
}

const round = (n, k = 5) => Math.round(n * 10 ** k) / 10 ** k;
function roundCoords(c, k) {
  return typeof c[0] === "number" ? [round(c[0], k), round(c[1], k)] : c.map((x) => roundCoords(x, k));
}

// d3 wants clockwise exterior rings; flip any polygon whose spherical area says it's inside-out.
export function rewindPolygon(rings) {
  const area = geoArea({ type: "Polygon", coordinates: rings });
  return area > 2 * Math.PI ? rings.map((r) => r.slice().reverse()) : rings;
}
function rewindGeometry(g) {
  if (g.type === "Polygon") return { type: "Polygon", coordinates: rewindPolygon(g.coordinates) };
  if (g.type === "MultiPolygon") return { type: "MultiPolygon", coordinates: g.coordinates.map(rewindPolygon) };
  return g;
}

function writeJSON(name, obj) {
  const p = path.join(GEO, name);
  fs.writeFileSync(p, JSON.stringify(obj));
  console.log(`wrote geo/${name} (${(fs.statSync(p).size / 1024).toFixed(0)} KB)`);
}
const need = (name) => FORCE || !fs.existsSync(path.join(GEO, name));

// --- US states (Census 1:500k cartographic boundaries, shoreline-clipped) ---
async function prepStates() {
  if (!need("us-states-500k.topo.json")) return;
  const zip = await download(SOURCES.states, path.join(RAW, "states500k.zip"));
  const dir = path.join(RAW, "states500k");
  fs.mkdirSync(dir, { recursive: true });
  execFileSync("unzip", ["-o", "-q", zip, "-d", dir]);
  const shp = fs.readdirSync(dir).find((f) => f.endsWith(".shp"));
  const fc = await shapefile.read(path.join(dir, shp), path.join(dir, shp.replace(/\.shp$/, ".dbf")));
  fc.features = fc.features.map((f) => ({
    type: "Feature",
    properties: { name: f.properties.NAME, abbr: f.properties.STUSPS },
    geometry: rewindGeometry(f.geometry),
  }));
  let topo = topology({ states: fc }, 1e6);
  topo = simplify(presimplify(topo), 2e-8);
  writeJSON("us-states-500k.topo.json", quantize(topo, 1e6));
}

// --- NYC borough shorelines (NYC Open Data) ---
async function prepBoroughs() {
  if (!need("nyc-boroughs.topo.json")) return;
  const raw = await download(SOURCES.boroughs, path.join(RAW, "boroughs.raw.geojson"));
  const fc = JSON.parse(fs.readFileSync(raw, "utf8"));
  const out = {
    type: "FeatureCollection",
    features: fc.features.map((f) => ({
      type: "Feature",
      properties: { name: f.properties.boroname || f.properties.BoroName },
      geometry: rewindGeometry({ type: f.geometry.type, coordinates: roundCoords(f.geometry.coordinates, 5) }),
    })),
  };
  let topo = topology({ b: out }, 1e6);
  topo = simplify(presimplify(topo), 1e-10);
  writeJSON("nyc-boroughs.topo.json", quantize(topo, 1e6));
}

// --- Lakes (Natural Earth 1:50m) so the Great Lakes read as water on both sides of the border ---
async function prepLakes() {
  if (!need("lakes-50m.json")) return;
  const raw = await download(SOURCES.lakes, path.join(RAW, "ne_50m_lakes.geojson"));
  const fc = JSON.parse(fs.readFileSync(raw, "utf8"));
  writeJSON("lakes-50m.json", {
    type: "FeatureCollection",
    features: fc.features
      .filter((f) => (f.properties.scalerank ?? 0) <= 3)
      .map((f) => ({ type: "Feature", properties: {}, geometry: rewindGeometry({ type: f.geometry.type, coordinates: roundCoords(f.geometry.coordinates, 3) }) })),
  });
}

// --- OSM parks + major roads inside the lens (Overpass) ---
function joinWays(ways) {
  // Stitch member ways into closed rings by matching endpoints.
  const key = (p) => `${p[0]},${p[1]}`;
  const pool = ways.map((w) => w.slice());
  const rings = [];
  while (pool.length) {
    let ring = pool.shift();
    let grew = true;
    while (key(ring[0]) !== key(ring[ring.length - 1]) && grew) {
      grew = false;
      for (let i = 0; i < pool.length; i++) {
        const w = pool[i];
        const end = key(ring[ring.length - 1]);
        if (key(w[0]) === end) ring = ring.concat(w.slice(1));
        else if (key(w[w.length - 1]) === end) ring = ring.concat(w.slice().reverse().slice(1));
        else continue;
        pool.splice(i, 1);
        grew = true;
        break;
      }
    }
    if (ring.length > 3 && key(ring[0]) === key(ring[ring.length - 1])) rings.push(ring);
  }
  return rings;
}

async function prepOSM() {
  if (!need("nyc-osm.topo.json")) return;
  const { s, w, n, e } = LENS_BBOX;
  const bb = `${s},${w},${n},${e}`;
  const q = `[out:json][timeout:120];(way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"](${bb});way["leisure"="park"](${bb});relation["leisure"="park"](${bb}););out geom;`;
  const rawPath = path.join(RAW, "osm.raw.json");
  try {
    await download(SOURCES.overpass, rawPath, {
      method: "POST",
      headers: { "User-Agent": "memmap-poster/1.0 (personal birthday gift)", Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
      body: "data=" + encodeURIComponent(q),
    });
  } catch (err) {
    console.warn("Overpass unavailable, poster will skip streets/parks:", err.message);
    writeJSON("nyc-osm.topo.json", topology({ osm: { type: "FeatureCollection", features: [] } }));
    return;
  }
  const osm = JSON.parse(fs.readFileSync(rawPath, "utf8"));
  const pt = (g) => [round(g.lon), round(g.lat)];
  const features = [];
  const ROADS = { motorway: 1, trunk: 1, primary: 2, secondary: 3, tertiary: 4 };
  for (const el of osm.elements) {
    const tags = el.tags || {};
    if (el.type === "way" && ROADS[tags.highway] && el.geometry) {
      if (tags.tunnel === "yes") continue;
      features.push({ type: "Feature", properties: { k: "road", r: ROADS[tags.highway], br: tags.bridge === "yes" ? 1 : 0 }, geometry: { type: "LineString", coordinates: el.geometry.map(pt) } });
    } else if (tags.leisure === "park") {
      let rings = [];
      if (el.type === "way" && el.geometry) {
        const r = el.geometry.map(pt);
        if (r.length > 3 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1]) rings = [r];
      } else if (el.type === "relation") {
        rings = joinWays(el.members.filter((m) => m.type === "way" && m.role !== "inner" && m.geometry).map((m) => m.geometry.map(pt)));
      }
      for (const r of rings) {
        features.push({ type: "Feature", properties: { k: "park", name: tags.name || "" }, geometry: { type: "Polygon", coordinates: rewindPolygon([r]) } });
      }
    }
  }
  writeJSON("nyc-osm.topo.json", topology({ osm: { type: "FeatureCollection", features } }, 1e6));
}

export async function prepGeo() {
  await prepStates();
  await prepBoroughs();
  await prepLakes();
  await prepOSM();
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await prepGeo();

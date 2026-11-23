#!/usr/bin/env node
// poll Renfe's GTFS-RT feed every minute, write raw protobufs to <outdir>/<utc>.pb
// usage: node collect_feed.cjs [outdir]  (default: feed_dumps)
"use strict";
const https = require("https");
const fs = require("fs");
const path = require("path");

const URLS = [
  "https://gtfsrt.renfe.com/trip_updates.pb",
  "https://gtfsrt.renfe.com/vehicle_positions.pb",
];
const outdir = process.argv[2] ?? "feed_dumps";
fs.mkdirSync(outdir, { recursive: true });

function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "rodalies-collect/0.1" } }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, body: Buffer.concat(chunks) }));
    }).on("error", reject);
  });
}

async function poll() {
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19) + "Z";
  for (const url of URLS) {
    const name = url.split("/").pop().replace(".pb", "");
    try {
      const { status, body } = await get(url);
      if (status !== 200) { console.error(ts, name, "HTTP", status); continue; }
      const dest = path.join(outdir, `${ts}_${name}.pb`);
      fs.writeFileSync(dest, body);
      console.log(ts, name, body.length, "bytes");
    } catch (e) {
      console.error(ts, name, e.message);
    }
  }
}

poll();
const ms = 60 * 1000;
setInterval(poll, ms);
console.log("collecting to", outdir, "every 60 s, ctrl-c to stop");

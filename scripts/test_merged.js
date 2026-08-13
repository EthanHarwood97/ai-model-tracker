const fs = require("fs");
const data = JSON.parse(fs.readFileSync("docs/data.json", "utf8"));
const all = [...(data.coding || []), ...(data.est || [])];
console.log("merged rows:", all.length);
const quality = (m) => Number(m.coding_index || 0);
const top = [...all].sort((a, b) => quality(b) - quality(a)).slice(0, 12);
for (const m of top) {
  const est = !m.measured ? "EST" : "  measured";
  console.log(`  ${quality(m).toFixed(1).padStart(5)}  ${est}  ${m.name.slice(0, 52)}`);
}

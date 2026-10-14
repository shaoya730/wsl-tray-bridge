// Optional artwork tooling: npm install --no-save --package-lock=false sharp
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

async function iconFrame(svg, size) {
  const rgba = await sharp(svg, { density: 384 }).resize(size, size).ensureAlpha().raw().toBuffer();
  const maskStride = Math.ceil(size / 32) * 4;
  const pixelsLength = size * size * 4;
  const dib = Buffer.alloc(40 + pixelsLength + maskStride * size);
  dib.writeUInt32LE(40, 0);
  dib.writeInt32LE(size, 4);
  dib.writeInt32LE(size * 2, 8);
  dib.writeUInt16LE(1, 12);
  dib.writeUInt16LE(32, 14);
  dib.writeUInt32LE(pixelsLength, 20);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const src = (y * size + x) * 4;
      const row = size - 1 - y;
      const dst = 40 + (row * size + x) * 4;
      dib[dst] = rgba[src + 2]; dib[dst + 1] = rgba[src + 1];
      dib[dst + 2] = rgba[src]; dib[dst + 3] = rgba[src + 3];
      if (rgba[src + 3] === 0) dib[40 + pixelsLength + row * maskStride + (x >> 3)] |= 0x80 >> (x & 7);
    }
  }
  return dib;
}

async function main() {
  const assets = path.resolve(__dirname, '../assets');
  const svg = fs.readFileSync(path.join(assets, 'icon.svg'));
  await sharp(svg, { density: 384 }).resize(512, 512).png().toFile(path.join(assets, 'icon.png'));
  const sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256];
  const frames = [];
  for (const size of sizes) {
    frames.push(await iconFrame(svg, size));
  }
  // DIB frames retain alpha and work with .NET Framework's System.Drawing.Icon.
  const header = Buffer.alloc(6 + 16 * sizes.length);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(sizes.length, 4);
  let offset = header.length;
  sizes.forEach((size, index) => {
    const entry = 6 + index * 16;
    header[entry] = size === 256 ? 0 : size;
    header[entry + 1] = size === 256 ? 0 : size;
    header.writeUInt16LE(1, entry + 4);
    header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(frames[index].length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += frames[index].length;
  });
  fs.writeFileSync(path.join(assets, 'icon.ico'), Buffer.concat([header, ...frames]));
  console.log('Exported icon.png and icon.ico (' + sizes.join(', ') + ' px)');
}

main().catch(error => { console.error(error); process.exitCode = 1; });

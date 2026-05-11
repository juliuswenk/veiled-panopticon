// ── INVISIBLE WAVES ──────────────────────────────────────────────────────────

// ╔══════════════════════════════════════════════════════╗
// ║  EINSTELLUNGEN – hier alles anpassen                ║
// ╚══════════════════════════════════════════════════════╝

// ── Figur ────────────────────────────────────────────────────────────────────
const BODY_COLS = 200; // horizontale Abtastpunkte (Auflösung der Körperkante) - höher = glatter
const BODY_ROWS = 300; // vertikale Abtastpunkte - höher = glatter
const FIGURE_SCALE = 0.8; // Gesamtgröße  (1 = passt in Bildschirm)
const FIGURE_WIDTH = 0.95; // Breite der Figur relativ zur Höhe  (1=quadratische Zellen, <1=schmaler, >1=breiter)
const FIGURE_CROP = 1; // Sichtbarer Anteil von oben  (0.7 = Oberschenkel aufwärts)
const LAG_SPEED = 0.7; // Wie schnell Figur der Maus folgt  (0=nie, 1=sofort)

// ── SVG-Silhouette ────────────────────────────────────────────────────────────
const USE_SVG = true; // true = SVG nutzen, false = prozedurale Form
const SVG_FILE = "figur.svg"; // Pfad zur SVG-Datei (muss im selben Ordner liegen)
//   SVG-Anforderungen: Silhouette gefüllt, transparenter Hintergrund
//   Benötigt lokalen Webserver (z.B. VS Code Live Server) – file:// funktioniert nicht

// ── Optik ────────────────────────────────────────────────────────────────────
const SCAN_H = 1; // Höhe einer Scan-Zeile in Pixeln
const WAVE_FREQ = 0.7; // Frequenz der Hintergrundwellen  (höher = enger)
const WAVE_SPEED = 0.6; // Geschwindigkeit der Wellen
const WAVE_FREQ2 = 0.4; // Zweite Wellenfrequenz für Interferenz
const CONTRAST = 4.5; // Kontrast der Wellen  (höher = mehr schwarz/weiß)
const WAVE_MIN = 95; // Minimale Helligkeit der Wellen  (0=schwarz, 255=weiß)
const FIGURE_BLUR = 40; // Blur-Radius der Figur in Pixeln  (0=scharf)

// ── Hintergrund-Raum ─────────────────────────────────────────────────────────
const ROOM_FILE = "Background Room.png";
const ROOM_ALPHA = 50;
const ROOM_GLITCH_CHANCE = 0.06;
const ROOM_GLITCH_BANDS = 4;
const ROOM_GLITCH_MAX_SHIFT = 80;
const ROOM_GLITCH_CHROMA_SHIFT = 10;

// ── Ghost-Effekt ──────────────────────────────────────────────────────────────
const GHOST_ALPHA = 230; // Silhouetten-Transparenz (0=unsichtbar, 255=voll)
const GHOST_EDGE = 68; // Weichheit der Kante in Pixeln
const GHOST_DRIFT = 0.5; // Max. Versatz pro Zeile (horizontale Geister-Streifen)
const GHOST_DRIFT_SPEED = 0.18; // Drift-Geschwindigkeit
const GHOST_STRETCH = 0; // Max. horizontale Zerrung pro Zeile (0=keine)

// ── Glitch ───────────────────────────────────────────────────────────────────
const GLITCH_BANDS = 19; // Max. gleichzeitige Glitch-Streifen
const GLITCH_STRENGTH = 170; // Verschiebung in Pixeln
const GLITCH_CHANCE = 0.6; // Wahrscheinlichkeit pro Frame  (0–1)
const GLITCH_H_MIN = 0.3; // Mindesthöhe eines Streifens (in Körper-Zeilen)
const GLITCH_H_MAX = 4; // Maximalhöhe eines Streifens

// ── Chromatische Aberration ───────────────────────────────────────────────────
const CHROMA_SPREAD = 11; // Pixel-Versatz der Farbkanäle an Körperkanten
const CHROMA_RGB_TEXT = 5; // RGB-Versatz für Text
const CHROMA_RGB_BOX = 7; // RGB-Versatz für Erkennungs-Boxen
const RGB_GLITCH_SPREAD = 4; // Zusätzlicher Glitch-Versatz zwischen RGB-Kanälen

// ── Erkennungs-Rechtecke ─────────────────────────────────────────────────────
const BOX_WEIGHT = 3.5; // Liniendicke (px)
const BOX_LAG_SPEED = 0.2; // Wie schnell Boxen dem Körper folgen  (0=nie, 1=sofort)
const BOX_JITTER = 3; // Max. zufälliger Versatz pro Frame (px)
const BOX_JUMP_CHANCE = 0.04; // Wahrscheinlichkeit eines harten Sprungs pro Frame (0–1)
const BOX_JUMP_DIST = 63; // Max. Sprungweite bei hartem Sprung (px)
// Position der Boxen als Anteil der Silhouettengröße  (0=oben/links, 1=unten/rechts)
const BOX_HEAD_X = 0.27;
const BOX_HEAD_Y = 0.0;
const BOX_HEAD_W = 0.34;
const BOX_HEAD_H = 0.35;
const BOX_BODY_X = 0.13;
const BOX_BODY_Y = 0.32;
const BOX_BODY_W = 0.78;
const BOX_BODY_H = 0.66;

// ── Hintergrund-Blobs ────────────────────────────────────────────────────────
const BLOB_SPAWN_CHANCE = 0.07; // Wahrscheinlichkeit pro Frame, dass ein neuer Blob erscheint
const BLOB_MAX_COUNT = 4; // Max. gleichzeitige Blobs
const BLOB_MIN_H = 0.15; // Minimale Höhe relativ zur Hauptfigur-Höhe
const BLOB_MAX_H = 0.7; // Maximale Höhe relativ zur Hauptfigur-Höhe
const BLOB_MIN_W = 0.08; // Minimale Breite relativ zur Hauptfigur-Höhe
const BLOB_MAX_W = 0.4; // Maximale Breite (wird auf Blob-Höhe begrenzt)
const BLOB_MIN_ALPHA = 110; // Minimale Transparenz
const BLOB_MAX_ALPHA = 205; // Maximale Transparenz
const BLOB_MIN_SPEED = 0.2; // Minimale Basisgeschwindigkeit
const BLOB_MAX_SPEED = 2.0; // Maximale Basisgeschwindigkeit
const BLOB_SPEED_JITTER = 3.0; // Noise-Stärke: wie stark die Geschwindigkeit schwankt (0=konstant)
const BLOB_DIR_CHANGE = 0.25; // Wahrscheinlichkeit pro Frame für spontanen Richtungswechsel
const BLOB_WARP_CHANCE = 0.2; // Wahrscheinlichkeit eines Positions-Sprungs pro Frame
const BLOB_WARP_DIST = 250; // Max. Sprungweite in Pixeln
const BLOB_MIN_LIFE = 0.05; // Minimale Lebensdauer in Sekunden
const BLOB_MAX_LIFE = 2.5; // Maximale Lebensdauer
const BLOB_FADE_T = 0.4; // Fade-In/Fade-Out-Dauer in Sekunden

// ── CRT / Screen Door Effect ─────────────────────────────────────────────────
const CRT_SCANLINE_ALPHA = 40; // Dunkelheit der horizontalen CRT-Zeilen  (0=aus, 255=schwarz)
const SCREEN_DOOR_ALPHA = 36; // Dunkelheit des vertikalen Pixel-Gitters  (0=aus, 255=schwarz)
const SCREEN_DOOR_CELL = 4; // Breite einer Pixel-Zelle in px  (z.B. 3 = 3px breit)

// ── Anzeige ──────────────────────────────────────────────────────────────────
const TEXT_SIZE = 31; // Schriftgröße Timestamp  (px)

// ── ESP32 / Input-Logik ──────────────────────────────────────────────────────
const CHANNEL_X = [0.07, 0.5, 0.93]; // X-Positionen für links, mitte, rechts
const MAX_FIGURES = 2; // Max. gleichzeitig sichtbare Figuren
const FIGURE_SLIDE_SPEED = 0.08; // Wie schnell Figur zur neuen Position slided
const TRANSITION_SPEED = 0.02; // Fortschritt der Transition pro Frame
const TRANSITION_ALPHA_DROP = 0.4; // Wie stark Alpha während Transition einbricht (0–1)
const TRANSITION_SCALE_DROP = 0.09; // Wie stark Scale während Transition einbricht (0–1)
const DEACTIVATE_HOLD_FRAMES = 20; // Frames, in denen Figur nach Kanaldeaktivierung Größe/Alpha hält
const FIGURE_SLOT_OFFSET = 0.025; // Normierter X-Versatz zwischen zwei Figuren am gleichen Kanal
const CSI_EVENTS_URL = "http://127.0.0.1:8765/events"; // Live-Daten aus rssi_presence_ui.py
const CSI_CHANNEL_ON_THRESHOLD = 0.05; // Kanal gilt als aktiv, sobald c > Schwellwert

// ─────────────────────────────────────────────────────────────────────────────

let svgImg = null;
let roomImg = null;
let svgGfx = null;
let figureGfx = null;
let blurGfx = null;

// Figuren-System (bis zu MAX_FIGURES gleichzeitig)
let figures = [];
let activeChannels = [false, false, false]; // links, mitte, rechts
let csiEventSource = null;
let csiChannelStates = [false, false, false];

class Figure {
  constructor(channel, startX) {
    this.channel = channel;
    this.targetX = CHANNEL_X[channel];
    this.currentX = startX !== undefined ? startX : this.targetX;
    this.targetAlpha = 1;
    this.currentAlpha = 1;
    this.targetScale = 1;
    this.currentScale = 1;
    this.transStartX = this.targetX;
    this.transEndX = this.targetX;
    this.holdTimer = 0;
    this.boxPos = this.targetX;
    this.boxOffsets = [
      { x: 0, y: 0 },
      { x: 0, y: 0 },
    ];
    this.flipX = random() < 0.5;
    this.scaleVar = random(0.9, 1.12);
    this.widthVar = random(0.85, 1.15);
  }

  reassign(channel) {
    this.transStartX = this.currentX;
    this.channel = channel;
    this.targetX = CHANNEL_X[channel];
    this.transEndX = this.targetX;
    this.targetAlpha = 1;
    this.targetScale = 1;
    this.holdTimer = 0;
  }

  update() {
    if (this.holdTimer > 0) {
      this.holdTimer--;
      this.boxPos += (this.currentX - this.boxPos) * BOX_LAG_SPEED;
      for (let b of this.boxOffsets) {
        b.x += random(-BOX_JITTER, BOX_JITTER);
        b.y += random(-BOX_JITTER, BOX_JITTER);
        if (random() < BOX_JUMP_CHANCE) {
          let angle = random(TWO_PI);
          let dist = random(BOX_JUMP_DIST * 0.5, BOX_JUMP_DIST);
          b.x += cos(angle) * dist;
          b.y += sin(angle) * dist;
        }
        b.x *= 0.55;
        b.y *= 0.55;
      }
      return;
    }

    this.currentX += (this.targetX - this.currentX) * FIGURE_SLIDE_SPEED;
    this.currentAlpha += (this.targetAlpha - this.currentAlpha) * 0.06;
    this.currentScale += (this.targetScale - this.currentScale) * 0.06;
    this.boxPos += (this.currentX - this.boxPos) * BOX_LAG_SPEED;

    for (let b of this.boxOffsets) {
      b.x += random(-BOX_JITTER, BOX_JITTER);
      b.y += random(-BOX_JITTER, BOX_JITTER);
      if (random() < BOX_JUMP_CHANCE) {
        let angle = random(TWO_PI);
        let dist = random(BOX_JUMP_DIST * 0.5, BOX_JUMP_DIST);
        b.x += cos(angle) * dist;
        b.y += sin(angle) * dist;
      }
      b.x *= 0.55;
      b.y *= 0.55;
    }
  }

  _transProgress() {
    let total = this.transEndX - this.transStartX;
    if (abs(total) < 0.001) return 1;
    return constrain((this.currentX - this.transStartX) / total, 0, 1);
  }

  getAlpha() {
    let drop = sin(this._transProgress() * PI) * TRANSITION_ALPHA_DROP;
    return this.currentAlpha * (1 - drop);
  }

  getScale() {
    let drop = sin(this._transProgress() * PI) * TRANSITION_SCALE_DROP;
    return this.currentScale * (1 - drop);
  }

  isFadingOut() {
    return this.targetAlpha < 0.5 && this.currentAlpha > 0.01;
  }

  isActive() {
    return this.currentAlpha > 0.01;
  }
}
let t = 0;
let cellH, silW, silW_base, silH, baseY;
let rowBounds = []; // { left, right } in [0..1]  pro Körper-Zeile
let glitchBands = [];
let ghostDrifts = []; // noise-basierter horizontaler Versatz pro Zeile
let ghostStretches = []; // noise-basierte Breitenverzerrung pro Zeile
let ghostAlphas = []; // noise-basierte Opazität pro Zeile
let blobs = [];

// ── SETUP ────────────────────────────────────────────────────────────────────

function preload() {
  if (USE_SVG) svgImg = loadImage(SVG_FILE);
  roomImg = loadImage(ROOM_FILE);
}

function setup() {
  createCanvas(windowWidth, windowHeight);
  noStroke();
  computeLayout();
  connectCsiInput();
}

function computeLayout() {
  // cellH: Pixel-Höhe einer Körper-Zeile
  cellH = (height * FIGURE_SCALE) / BODY_ROWS;
  // silW: physische Breite der Figur – gleiche Zellgröße in x wie in y
  silW_base = BODY_COLS * cellH; // Positionierungsbreite (unverändert)
  silW = silW_base * FIGURE_WIDTH; // Segmentbreite (skaliert)
  silH = BODY_ROWS * cellH;
  baseY = height - FIGURE_CROP * silH;
  if (USE_SVG && svgImg) buildSVGBuffer();
  precomputeBounds();
  if (figureGfx) figureGfx.remove();
  figureGfx = createGraphics(width, height);
  figureGfx.pixelDensity(1);
  figureGfx.noStroke();
  if (blurGfx) blurGfx.remove();
  blurGfx = createGraphics(width, height);
  blurGfx.pixelDensity(1);
  blurGfx.noStroke();
}

// SVG in einen BODY_COLS×BODY_ROWS Puffer rendern und Pixel laden
function buildSVGBuffer() {
  if (svgGfx) svgGfx.remove();
  svgGfx = createGraphics(BODY_COLS, BODY_ROWS);
  svgGfx.pixelDensity(1); // Buffer immer exakt BODY_COLS×BODY_ROWS, unabhängig von HiDPI/Windows-Skalierung
  svgGfx.clear();
  svgGfx.image(svgImg, 0, 0, BODY_COLS, BODY_ROWS);
  try {
    svgGfx.loadPixels();
    console.log("SVG geladen, Pixel-Buffer: " + BODY_COLS + "×" + BODY_ROWS);
  } catch (e) {
    console.error(
      "SVG-Pixel konnten nicht gelesen werden – kein Webserver? Fallback auf prozedurale Form.",
    );
    svgGfx = null;
  }
}

// Körper-Grenzen für jede Zeile vorberechnen – mehrere Segmente pro Zeile möglich
function precomputeBounds() {
  rowBounds = [];
  for (let r = 0; r < BODY_ROWS; r++) {
    let ny = r / (BODY_ROWS - 1);
    let segments = [];
    let inSeg = false,
      segStart = 0;

    for (let c = 0; c < BODY_COLS; c++) {
      let inside =
        USE_SVG && svgGfx
          ? svgGfx.pixels[(r * BODY_COLS + c) * 4 + 3] > 128
          : isBody(c / (BODY_COLS - 1), ny);

      if (inside && !inSeg) {
        inSeg = true;
        segStart = c;
      } else if (!inside && inSeg) {
        inSeg = false;
        segments.push({
          left: segStart / (BODY_COLS - 1),
          right: (c - 1) / (BODY_COLS - 1),
        });
      }
    }
    if (inSeg) segments.push({ left: segStart / (BODY_COLS - 1), right: 1 });

    rowBounds.push(segments.length > 0 ? segments : null);
  }
}

// Körperform in normalisiertem [0,1]-Koordinatensystem
function isBody(x, y) {
  const m = 0.5;
  const ell = (cx, cy, rx, ry) =>
    ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < 1;

  // Weichere Übergänge mit abgerundeten Formen
  const softBox = (cx, cy, w, h, roundness = 0.3) => {
    let dx = abs(x - cx);
    let dy = abs(y - cy);
    let rx = w * 0.5;
    let ry = h * 0.5;

    // Ecken abrunden
    if (dx > rx * (1 - roundness) && dy > ry * (1 - roundness)) {
      let cornerX = rx * (1 - roundness);
      let cornerY = ry * (1 - roundness);
      let edx = (dx - cornerX) / (rx * roundness);
      let edy = (dy - cornerY) / (ry * roundness);
      return edx * edx + edy * edy < 1;
    }
    return dx < rx && dy < ry;
  };

  return (
    // Kopf (Ellipse)
    ell(m, 0.077, 0.11, 0.075) ||
    // Hals (weiche Form)
    softBox(m, 0.165, 0.088, 0.05, 0.4) ||
    // Schultern (Ellipse)
    ell(m, 0.24, 0.21, 0.062) ||
    // Oberkörper/Torso (weiche rechteckige Form)
    softBox(m, 0.355, 0.296, 0.33, 0.25) ||
    // Linker Arm (Oberarm)
    softBox(m - 0.2, 0.32, 0.13, 0.24, 0.35) ||
    // Rechter Arm (Oberarm)
    softBox(m + 0.2, 0.32, 0.13, 0.24, 0.35) ||
    // Linker Unterarm
    softBox(m - 0.2175, 0.565, 0.125, 0.27, 0.4) ||
    // Rechter Unterarm
    softBox(m + 0.2175, 0.565, 0.125, 0.27, 0.4) ||
    // Hüfte/Taille (Ellipse für weichen Übergang)
    ell(m, 0.575, 0.165, 0.057) ||
    // Becken (weiche Form)
    softBox(m, 0.655, 0.304, 0.09, 0.3) ||
    // Linkes Bein (Oberschenkel)
    softBox(m - 0.0825, 0.7, 0.139, 0.18, 0.35) ||
    // Rechtes Bein (Oberschenkel)
    softBox(m + 0.0825, 0.7, 0.139, 0.18, 0.35) ||
    // Linkes Bein (Unterschenkel)
    softBox(m - 0.075, 0.865, 0.11, 0.17, 0.35) ||
    // Rechtes Bein (Unterschenkel)
    softBox(m + 0.075, 0.865, 0.11, 0.17, 0.35) ||
    // Linker Fuß (Ellipse)
    ell(m - 0.085, 0.962, 0.062, 0.025) ||
    // Rechter Fuß (Ellipse)
    ell(m + 0.085, 0.962, 0.062, 0.025)
  );
}

// ── DRAW ─────────────────────────────────────────────────────────────────────

function draw() {
  background(0);
  t += 0.006;

  // Figuren updaten & tote entfernen
  for (let i = figures.length - 1; i >= 0; i--) {
    figures[i].update();
    if (
      figures[i].currentAlpha < 0.005 &&
      !activeChannels[figures[i].channel]
    ) {
      figures.splice(i, 1);
    }
  }

  // Blobs spawnen
  if (random() < BLOB_SPAWN_CHANCE && blobs.length < BLOB_MAX_COUNT) {
    blobs.push(new Blob());
  }
  // Blobs updaten & tote entfernen
  for (let i = blobs.length - 1; i >= 0; i--) {
    if (blobs[i].update(1 / 60)) {
      blobs.splice(i, 1);
    }
  }

  updateGlitch();
  updateGhostFields();

  drawWaves(0);
  drawRoomBackground();

  // Buffer: zuerst Blobs (hinter)
  figureGfx.clear();
  for (let blob of blobs) {
    blob.render(figureGfx);
  }

  // Dann jede aktive Figur zeichnen (nur wenn noch sichtbar)
  for (let fig of figures) {
    if (fig.getAlpha() < 0.03) continue;
    let margin = silW_base / 2 + 30;
    let baseX =
      map(fig.currentX + figSlotOffset(fig), 0, 1, margin, width - margin) -
      silW_base / 2;
    drawFigure(
      baseX,
      fig.getAlpha(),
      fig.getScale() * fig.scaleVar,
      fig.flipX,
      fig.widthVar,
    );
  }

  drawFigureBuffer();
  drawScanlines(); // CRT Scan-Zeilen-Overlay

  // Blob-Tracking-Rechtecke
  for (let blob of blobs) {
    blob.drawBox();
  }

  // Erkennungs-Rechtecke für jede Figur (nur wenn noch sichtbar)
  for (let fig of figures) {
    if (fig.getAlpha() < 0.3) continue;
    let margin = silW_base / 2 + 30;
    let boxBaseX =
      map(fig.boxPos + figSlotOffset(fig), 0, 1, margin, width - margin) -
      silW_base / 2;
    drawDetectionBoxes(boxBaseX, fig);
  }

  drawTimestamp();
}

// ── Hintergrund + Silhouette ──────────────────────────────────────────────────

function waveBrightness(y) {
  let w1 = (sin(y * WAVE_FREQ * TWO_PI + t * WAVE_SPEED * TWO_PI) + 1) * 0.5;
  let w2 =
    (sin(y * WAVE_FREQ2 * TWO_PI - t * WAVE_SPEED * TWO_PI * 0.6) + 1) * 0.5;
  let n = noise(y * 0.005, t * 0.08);
  let v = w1 * w2 * 0.6 + n * 0.4;
  return pow(constrain(v, 0, 1), CONTRAST);
}

function roomCoverRect() {
  if (!roomImg || roomImg.width <= 0 || roomImg.height <= 0) return null;
  const scale = max(width / roomImg.width, height / roomImg.height);
  const dw = roomImg.width * scale;
  const dh = roomImg.height * scale;
  return {
    x: (width - dw) * 0.5,
    y: (height - dh) * 0.5,
    w: dw,
    h: dh,
    scale,
  };
}

function drawRoomBackground() {
  const rect = roomCoverRect();
  if (!rect) return;

  push();
  blendMode(ADD);
  tint(170, 255, 232, ROOM_ALPHA);
  image(roomImg, rect.x, rect.y, rect.w, rect.h);

  if (random() < ROOM_GLITCH_CHANCE) {
    drawRoomGlitch(rect);
  }

  noTint();
  blendMode(BLEND);
  pop();
}

function drawRoomGlitch(rect) {
  const bands = floor(random(2, ROOM_GLITCH_BANDS + 1));
  for (let i = 0; i < bands; i++) {
    const bandH = random(6, height * 0.08);
    const bandY = random(0, height - bandH);
    const shift = random(-ROOM_GLITCH_MAX_SHIFT, ROOM_GLITCH_MAX_SHIFT);
    const sx = 0;
    const sy = constrain((bandY - rect.y) / rect.scale, 0, roomImg.height);
    const sw = roomImg.width;
    const sh = constrain(bandH / rect.scale, 1, roomImg.height - sy);

    tint(180, 255, 235, random(130, 230));
    image(roomImg, rect.x + shift, bandY, rect.w, bandH, sx, sy, sw, sh);

    tint(255, 80, 120, random(35, 90));
    image(
      roomImg,
      rect.x + shift - ROOM_GLITCH_CHROMA_SHIFT,
      bandY,
      rect.w,
      bandH,
      sx,
      sy,
      sw,
      sh,
    );

    tint(70, 150, 255, random(35, 90));
    image(
      roomImg,
      rect.x + shift + ROOM_GLITCH_CHROMA_SHIFT,
      bandY,
      rect.w,
      bandH,
      sx,
      sy,
      sw,
      sh,
    );
  }
}

function drawFigureBuffer() {
  if (FIGURE_BLUR <= 0) {
    image(figureGfx, 0, 0);
    return;
  }

  blurGfx.clear();
  blurGfx.image(figureGfx, 0, 0);
  blurGfx.filter(BLUR, FIGURE_BLUR);
  image(blurGfx, 0, 0);
}

function getGlitchDX(r) {
  for (let b of glitchBands) {
    if (r >= b.r0 && r <= b.r1) return b.dx;
  }
  return 0;
}

function getGlitchPink(r) {
  for (let b of glitchBands) {
    if (r >= b.r0 && r <= b.r1) return b.pink;
  }
  return 0;
}

function getGlitchGreen(r) {
  for (let b of glitchBands) {
    if (r >= b.r0 && r <= b.r1) return b.neonGreen || 0;
  }
  return 0;
}

// Noise-Felder für Ghost-Effekt einmal pro Frame vorberechnen
function updateGhostFields() {
  ghostDrifts = [];
  ghostStretches = [];
  ghostAlphas = [];
  for (let r = 0; r < BODY_ROWS; r++) {
    // horizontaler Versatz: langsam driftende Streifen
    ghostDrifts.push(
      (noise(r * 0.06, t * GHOST_DRIFT_SPEED) - 0.5) * 2 * GHOST_DRIFT,
    );
    // Breitenverzerrung: zerrt einzelne Zeilen leicht horizontal
    ghostStretches.push(
      1 + noise(r * 0.04 + 100, t * GHOST_DRIFT_SPEED * 0.6) * GHOST_STRETCH,
    );
    // Opazität: subtiles Pulsieren entlang der Figur
    ghostAlphas.push(
      GHOST_ALPHA * (0.5 + 0.5 * noise(r * 0.05 + 200, t * 0.1)),
    );
  }
}

function drawWaves(baseX) {
  noStroke();
  for (let y = 0; y < height; y += SCAN_H) {
    let ny = (y - baseY) / silH;
    let r = round(ny * (BODY_ROWS - 1));
    let gdx = r >= 0 && r < BODY_ROWS ? getGlitchDX(r) : 0;
    let bv = waveBrightness(y + gdx * 0.15);
    let pink = getGlitchPink(r);
    let green = getGlitchGreen(r);
    fill(
      lerp(WAVE_MIN, 200 + 30 * pink, bv) + 40 * pink - 180 * green * bv,
      lerp(WAVE_MIN * 1.1, 255 - 40 * pink, bv),
      lerp(WAVE_MIN, 220 - 60 * pink, bv) - 180 * green * bv,
    );
    rect(0, y, width, SCAN_H);
  }
}

function drawFigure(baseX, figAlpha, figScale, flipX, widthVar) {
  figAlpha = figAlpha !== undefined ? figAlpha : 1;
  figScale = figScale !== undefined ? figScale : 1;
  flipX = flipX || false;
  widthVar = widthVar !== undefined ? widthVar : 1;

  // Untere Kante bleibt fest – Skalierung nur nach oben
  let scaledBaseY = baseY + silH * (1 - figScale);

  for (let y = 0; y < height; y += SCAN_H) {
    let ny = (y - scaledBaseY) / (silH * figScale);
    let r = round(ny * (BODY_ROWS - 1));
    if (r < 0 || r >= BODY_ROWS) continue;
    let segments = rowBounds[r];
    if (!segments) continue;

    let gdx = getGlitchDX(r);
    let ghostDX = ghostDrifts[r];
    let stretch = ghostStretches[r];
    let alpha = ghostAlphas[r];

    for (let seg of segments) {
      let normCenter = flipX
        ? 1 - (seg.left + seg.right) * 0.5
        : (seg.left + seg.right) * 0.5;
      let centerX = baseX + normCenter * silW_base + gdx + ghostDX;
      let hw = (seg.right - seg.left) * silW * widthVar * 0.5 * stretch;
      let bx = centerX - hw;
      let bw = hw * 2;

      let rOff = sin(t * 3.1 + r * 0.2) * RGB_GLITCH_SPREAD;
      let gOff = sin(t * 2.3 + r * 0.3 + 1.7) * RGB_GLITCH_SPREAD;
      let bOff = sin(t * 2.7 + r * 0.25 + 3.3) * RGB_GLITCH_SPREAD;

      let aMult = figAlpha;
      figureGfx.fill(0, 76, 71, 80 * aMult);
      figureGfx.rect(bx - CHROMA_SPREAD + rOff, y, bw, SCAN_H);
      figureGfx.fill(88, 129, 216, 65 * aMult);
      figureGfx.rect(bx + CHROMA_SPREAD + bOff, y, bw, SCAN_H);
      figureGfx.fill(
        76 * 0.5 + 129 * 0.3,
        76 * 0.3 + 129 * 0.5,
        71 * 0.5 + 216 * 0.3,
        50 * aMult,
      );
      figureGfx.rect(bx + gOff * 0.5, y, bw, SCAN_H);

      if (FIGURE_BLUR > 0) {
        figureGfx.fill(0, 0, 0, GHOST_ALPHA * aMult);
        figureGfx.rect(bx, y, bw, SCAN_H);
      } else {
        for (let s = 1; s <= 4; s++) {
          let ew = GHOST_EDGE * (1 - s / 4);
          let ea = alpha * (s / 4) * aMult;
          figureGfx.fill(0, 0, 0, ea);
          figureGfx.rect(bx - ew, y, bw + ew * 2, SCAN_H);
        }
      }
    }
  }
}

// ── CRT-Overlay ──────────────────────────────────────────────────────────────

function drawScanlines() {
  noStroke();
  if (CRT_SCANLINE_ALPHA > 0) {
    fill(0, 0, 0, CRT_SCANLINE_ALPHA);
    for (let y = 0; y < height; y += 2) {
      rect(0, y, width, 1);
    }
  }
  if (SCREEN_DOOR_ALPHA > 0) {
    // RGB-Subpixel-Streifen wie Phosphor-Masken bei alten CRT-Röhrenfernsehern
    let sub = SCREEN_DOOR_CELL / 3;
    const subColors = [
      [255, 0, 0],
      [0, 255, 0],
      [0, 0, 255],
    ];
    for (let x = 0; x < width; x += SCREEN_DOOR_CELL) {
      for (let i = 0; i < 3; i++) {
        let [r, g, b] = subColors[i];
        fill(r, g, b, SCREEN_DOOR_ALPHA);
        rect(x + i * sub, 0, sub, height);
      }
    }
  }
}

// ── Erkennungs-Rechtecke ─────────────────────────────────────────────────────

function drawDetectionBoxes(baseX, fig) {
  strokeWeight(BOX_WEIGHT);
  noFill();

  drawGlitchedBox(
    baseX + BOX_HEAD_X * silW_base + fig.boxOffsets[0].x,
    baseY + BOX_HEAD_Y * silH + fig.boxOffsets[0].y,
    BOX_HEAD_W * silW_base,
    BOX_HEAD_H * silH,
  );
  drawGlitchedBox(
    baseX + BOX_BODY_X * silW_base + fig.boxOffsets[1].x,
    baseY + BOX_BODY_Y * silH + fig.boxOffsets[1].y,
    BOX_BODY_W * silW_base,
    BOX_BODY_H * silH,
  );

  noStroke();
}

// Box zeilenweise mit Glitch-Versatz zeichnen
function drawGlitchedBox(x0, y0, w, h) {
  let glitchPhase = t * 5.7;
  let channels = [
    { r: 255, g: 60, b: 60, off: sin(glitchPhase) * RGB_GLITCH_SPREAD },
    { r: 0, g: 185, b: 50, off: sin(glitchPhase + 2.1) * RGB_GLITCH_SPREAD },
    { r: 0, g: 150, b: 120, off: sin(glitchPhase + 4.2) * RGB_GLITCH_SPREAD },
  ];

  for (let ch of channels) {
    let cOff = ch.off;

    // Obere Kante
    let rTop = constrain(
      round(((y0 - baseY) / silH) * (BODY_ROWS - 1)),
      0,
      BODY_ROWS - 1,
    );
    let dxTop = getGlitchDX(rTop) + cOff;
    stroke(ch.r, ch.g, ch.b, 220);
    line(x0 + dxTop, y0, x0 + w + dxTop, y0);

    // Untere Kante
    let rBot = constrain(
      round(((y0 + h - baseY) / silH) * (BODY_ROWS - 1)),
      0,
      BODY_ROWS - 1,
    );
    let dxBot = getGlitchDX(rBot) + cOff;
    line(x0 + dxBot, y0 + h, x0 + w + dxBot, y0 + h);

    // Linke + rechte Kante
    let prevR = -1,
      segY = y0;
    for (let y = y0; y <= y0 + h + 1; y++) {
      let r = constrain(
        round(((y - baseY) / silH) * (BODY_ROWS - 1)),
        0,
        BODY_ROWS - 1,
      );
      if (r !== prevR) {
        if (prevR >= 0) {
          let dx = getGlitchDX(prevR) + cOff;
          line(x0 + dx, segY, x0 + dx, y);
          line(x0 + w + dx, segY, x0 + w + dx, y);
        }
        prevR = r;
        segY = y;
      }
    }
  }
}

// ── Blob-Klasse für Hintergrund-Silhouetten ──────────────────────────────────

class Blob {
  constructor() {
    this.type = random(["figure", "circle", "oval"]);
    this.blobH = silH * random(BLOB_MIN_H, BLOB_MAX_H);
    this.blobW = min(silH * random(BLOB_MIN_W, BLOB_MAX_W), this.blobH);
    this.blobRows = round(BODY_ROWS * (this.blobH / silH));

    let margin = silW_base / 2 + 50;
    this.baseX = random(margin, width - margin);
    this.y = baseY + random(silH * 0.05, silH * 0.7);

    this.direction = random() < 0.5 ? -1 : 1;
    this.speed = random(BLOB_MIN_SPEED, BLOB_MAX_SPEED) * cellH * 3;
    this.noiseOff = random(1000);

    this.life = random(BLOB_MIN_LIFE, BLOB_MAX_LIFE);
    this.elapsed = 0;

    this.maxAlpha = random(BLOB_MIN_ALPHA, BLOB_MAX_ALPHA);
    this.alpha = 0;

    this.rowBounds = [];
    this._computeBounds();

    this.boxOffsets = { x: 0, y: 0 };
  }

  _computeBounds() {
    let rows = max(this.blobRows, 8);
    let cols = round(this.blobRows * (this.blobW / this.blobH));

    for (let r = 0; r < rows; r++) {
      let ny = r / (rows - 1);
      let segments = [];

      if (this.type === "circle") {
        let cy = 0.5,
          cr = 0.5;
        let dy = abs(ny - cy);
        if (dy < cr) {
          let hw = sqrt(cr * cr - dy * dy);
          segments.push({ left: 0.5 - hw, right: 0.5 + hw });
        }
      } else if (this.type === "oval") {
        let cx = 0.5,
          cy = 0.5,
          rx = 0.6,
          ry = 0.5;
        let v = ((ny - cy) / ry) ** 2;
        if (v < 1) {
          let hw = sqrt(1 - v) * rx;
          segments.push({ left: cx - hw, right: cx + hw });
        }
      } else {
        let inSeg = false,
          segStart = 0;
        for (let c = 0; c < cols; c++) {
          let nx = c / max(cols - 1, 1);
          let inside = isBody(nx, ny);
          if (inside && !inSeg) {
            inSeg = true;
            segStart = c;
          } else if (!inside && inSeg) {
            inSeg = false;
            segments.push({
              left: segStart / max(cols - 1, 1),
              right: (c - 1) / max(cols - 1, 1),
            });
          }
        }
        if (inSeg)
          segments.push({
            left: segStart / max(cols - 1, 1),
            right: 1,
          });
      }

      this.rowBounds.push(segments.length > 0 ? segments : null);
    }
  }

  update(dt) {
    this.elapsed += dt;
    let speedMult = map(
      noise(this.noiseOff + this.elapsed * 2),
      0,
      1,
      -BLOB_SPEED_JITTER,
      BLOB_SPEED_JITTER,
    );
    this.baseX += this.speed * this.direction * speedMult;
    if (random() < BLOB_DIR_CHANGE) this.direction *= -1;
    if (random() < BLOB_WARP_CHANCE)
      this.baseX += random(-BLOB_WARP_DIST, BLOB_WARP_DIST);

    this.boxOffsets.x += random(-BOX_JITTER * 0.4, BOX_JITTER * 0.4);
    this.boxOffsets.y += random(-BOX_JITTER * 0.4, BOX_JITTER * 0.4);
    if (random() < BOX_JUMP_CHANCE * 0.5) {
      this.boxOffsets.x +=
        (random() < 0.5 ? -1 : 1) *
        random(BOX_JUMP_DIST * 0.3, BOX_JUMP_DIST * 0.6);
      this.boxOffsets.y +=
        (random() < 0.5 ? -1 : 1) *
        random(BOX_JUMP_DIST * 0.3, BOX_JUMP_DIST * 0.6);
    }
    this.boxOffsets.x *= 0.6;
    this.boxOffsets.y *= 0.6;

    let fadeInEnd = BLOB_FADE_T;
    let fadeOutStart = this.life - BLOB_FADE_T;

    if (this.elapsed < fadeInEnd) {
      this.alpha = map(this.elapsed, 0, fadeInEnd, 0, this.maxAlpha, true);
    } else if (this.elapsed < fadeOutStart) {
      this.alpha = this.maxAlpha;
    } else {
      this.alpha = map(
        this.elapsed,
        fadeOutStart,
        this.life,
        this.maxAlpha,
        0,
        true,
      );
    }

    return this.elapsed >= this.life;
  }

  _globalRow(localRow) {
    let ny = localRow / max(this.blobRows - 1, 1);
    return constrain(
      round(((this.y + ny * this.blobH - baseY) / silH) * (BODY_ROWS - 1)),
      0,
      BODY_ROWS - 1,
    );
  }

  render(gfx) {
    if (this.alpha < 1) return;
    let rows = this.rowBounds.length;
    let s = this.blobH / silH;

    for (let py = 0; py < height; py += SCAN_H) {
      let ny = (py - this.y) / this.blobH;
      let r = round(ny * (rows - 1));
      if (r < 0 || r >= rows) continue;
      let segments = this.rowBounds[r];
      if (!segments) continue;

      let gR = this._globalRow(r);
      let gdx = getGlitchDX(gR);
      let ghostDX = ghostDrifts[gR] * s * 0.5;
      let stretch = 1 + (ghostStretches[gR] - 1) * s * 0.4;

      for (let seg of segments) {
        let centerX =
          this.baseX +
          (seg.left + seg.right) * 0.5 * this.blobW +
          gdx +
          ghostDX;
        let hw = (seg.right - seg.left) * this.blobW * 0.5 * stretch;
        let bx = centerX - hw;
        let bw = hw * 2;

        let rOff = sin(t * 3.1 + r * 0.2) * RGB_GLITCH_SPREAD * s;
        let gOff = sin(t * 2.3 + r * 0.3 + 1.7) * RGB_GLITCH_SPREAD * s;
        let bOff = sin(t * 2.7 + r * 0.25 + 3.3) * RGB_GLITCH_SPREAD * s;

        let chroma = CHROMA_SPREAD * s;
        let a = this.alpha;

        gfx.fill(0, 76, 71, a * 0.55);
        gfx.rect(bx - chroma + rOff, py, bw, SCAN_H);
        gfx.fill(88, 129, 216, a * 0.45);
        gfx.rect(bx + chroma + bOff, py, bw, SCAN_H);
        gfx.fill(0, 0, 0, a * 0.7);
        gfx.rect(bx + gOff * 0.5, py, bw, SCAN_H);

        if (FIGURE_BLUR > 0) {
          gfx.fill(0, 0, 0, a * 0.85);
          gfx.rect(bx, py, bw, SCAN_H);
        } else {
          for (let e = 1; e <= 4; e++) {
            let ew = GHOST_EDGE * (1 - e / 4) * s;
            let ea = a * (e / 4) * 0.3;
            gfx.fill(0, 0, 0, ea);
            gfx.rect(bx - ew, py, bw + ew * 2, SCAN_H);
          }
        }
      }
    }
  }

  drawBox() {
    if (this.alpha < 10) return;
    let bx = this.baseX + this.boxOffsets.x;
    let by = this.y + this.boxOffsets.y;

    // Obere Kante
    let rTop = constrain(
      round(((by - baseY) / silH) * (BODY_ROWS - 1)),
      0,
      BODY_ROWS - 1,
    );
    let dxTop = getGlitchDX(rTop);

    // Untere Kante
    let rBot = constrain(
      round(((by + this.blobH - baseY) / silH) * (BODY_ROWS - 1)),
      0,
      BODY_ROWS - 1,
    );
    let dxBot = getGlitchDX(rBot);

    let ghostPhase = t * 5.7;
    let channels = [
      { r: 255, g: 60, b: 60, off: sin(ghostPhase) * RGB_GLITCH_SPREAD },
      { r: 0, g: 185, b: 50, off: sin(ghostPhase + 2.1) * RGB_GLITCH_SPREAD },
      { r: 0, g: 150, b: 120, off: sin(ghostPhase + 4.2) * RGB_GLITCH_SPREAD },
    ];

    let a = map(this.alpha, BLOB_MIN_ALPHA, BLOB_MAX_ALPHA, 80, 220, true);

    for (let ch of channels) {
      stroke(ch.r, ch.g, ch.b, a);
      strokeWeight(BOX_WEIGHT);
      noFill();
      line(bx + dxTop + ch.off, by, bx + this.blobW + dxTop + ch.off, by);
      line(
        bx + dxBot + ch.off,
        by + this.blobH,
        bx + this.blobW + dxBot + ch.off,
        by + this.blobH,
      );

      let prevR = -1,
        segY = by;
      for (let py = by; py <= by + this.blobH + 1; py++) {
        let r = constrain(
          round(((py - baseY) / silH) * (BODY_ROWS - 1)),
          0,
          BODY_ROWS - 1,
        );
        if (r !== prevR) {
          if (prevR >= 0) {
            let dx = getGlitchDX(prevR) + ch.off;
            line(bx + dx, segY, bx + dx, py);
            line(bx + this.blobW + dx, segY, bx + this.blobW + dx, py);
          }
          prevR = r;
          segY = py;
        }
      }
    }
  }

  isDead() {
    return this.elapsed >= this.life;
  }
}

// ── Glitch ───────────────────────────────────────────────────────────────────

function updateGlitch() {
  if (random() < GLITCH_CHANCE && glitchBands.length < GLITCH_BANDS) {
    let r0 = floor(random(BODY_ROWS));
    let h = floor(random(GLITCH_H_MIN, GLITCH_H_MAX + 1));
    glitchBands.push({
      r0,
      r1: min(r0 + h, BODY_ROWS - 1),
      dx:
        (random() < 0.5 ? 1 : -1) *
        random(GLITCH_STRENGTH * 0.4, GLITCH_STRENGTH),
      life: floor(random(2, 8)),
      pink: random() < 0.05 ? random(0.7, 1.0) : random(0, 0.2), // 5% stark pink, rest minimal
      neonGreen: random() < 0.3 ? random(0.6, 1.0) : 0, // 30% neon grün
    });
  }
  for (let i = glitchBands.length - 1; i >= 0; i--) {
    if (--glitchBands[i].life <= 0) glitchBands.splice(i, 1);
  }
}

// ── Timestamp ────────────────────────────────────────────────────────────────

function drawTimestamp() {
  let now = new Date();
  let pad = (n) => String(n).padStart(2, "0");
  let txt =
    pad(now.getDate()) +
    "-" +
    pad(now.getMonth() + 1) +
    "-" +
    now.getFullYear() +
    "   " +
    pad(now.getHours()) +
    ":" +
    pad(now.getMinutes()) +
    ":" +
    pad(now.getSeconds());

  let textY = height - 18;
  let r = constrain(
    round(((textY - baseY) / silH) * (BODY_ROWS - 1)),
    0,
    BODY_ROWS - 1,
  );
  let baseDx = getGlitchDX(r);
  if (random() < 0.06) baseDx += (random() < 0.5 ? 1 : -1) * random(8, 45);

  let glitchPhase = t * 4.3;
  let channels = [
    {
      color: "rgba(255, 60, 60, 0.75)",
      off: sin(glitchPhase) * RGB_GLITCH_SPREAD,
    },
    {
      color: "rgba(150, 210, 160, 0.65)",
      off: sin(glitchPhase + 2.1) * RGB_GLITCH_SPREAD,
    },
    {
      color: "rgba(0, 150, 120, 0.70)",
      off: sin(glitchPhase + 4.2) * RGB_GLITCH_SPREAD,
    },
  ];

  let ctx = drawingContext;
  ctx.save();
  ctx.font = TEXT_SIZE + 'px "OCR A Extended", "OCR A", "OCR-A", monospace';
  ctx.globalCompositeOperation = "screen";
  for (let ch of channels) {
    ctx.fillStyle = ch.color;
    ctx.fillText(txt, 20 + baseDx + ch.off, textY);
  }
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "rgba(0, 185, 55, 1.0)";
  ctx.fillText(txt, 20 + baseDx, textY);
  ctx.restore();
}

// ── Input-Handler ─────────────────────────────────────────────────────────────

// Visuellen X-Versatz berechnen wenn mehrere Figuren am gleichen Kanal stehen
function figSlotOffset(fig) {
  let rank = 0,
    total = 0;
  for (let other of figures) {
    if (other.channel === fig.channel && other.getAlpha() >= 0.03) {
      if (other === fig) rank = total;
      total++;
    }
  }
  return total > 1 ? (rank - (total - 1) / 2) * FIGURE_SLOT_OFFSET : 0;
}

function handleChannelPress(channel) {
  if (activeChannels[channel]) return; // Kanal bereits aktiv

  if (channel !== 1) {
    // ── Randkanal (links / rechts) ──────────────────────────────────────────
    // 1. Gleichen Kanal reaktivieren falls noch sichtbar
    for (let fig of figures) {
      if (fig.channel === channel && fig.isActive()) {
        fig.targetAlpha = 1;
        fig.targetScale = 1;
        fig.holdTimer = 0;
        fig.targetX = CHANNEL_X[channel];
        activeChannels[channel] = true;
        return;
      }
    }
    // 2. Wenn Mitte aktiv und noch Platz: neue Figur an der Seite spawnen (Mitte behalten)
    let hasCenterFig = false;
    for (let fig of figures) {
      if (fig.channel === 1 && fig.currentAlpha > 0.01) {
        hasCenterFig = true;
        break;
      }
    }
    if (hasCenterFig && figures.length < MAX_FIGURES) {
      let startX = channel === 0 ? -0.15 : 1.15;
      figures.push(new Figure(channel, startX));
      activeChannels[channel] = true;
      return;
    }
    // 3. Mitte-Figur zum Rand umleiten (wenn da und kein Platz mehr)
    if (hasCenterFig) {
      for (let fig of figures) {
        if (fig.channel === 1 && fig.currentAlpha > 0.01) {
          fig.reassign(channel);
          activeChannels[channel] = true;
          return;
        }
      }
    }
    // 4. Noch Platz → neue Figur spawnen (zwei Randfiguren gleichzeitig möglich)
    let startX = channel === 0 ? -0.15 : 1.15;
    if (figures.length < MAX_FIGURES) {
      figures.push(new Figure(channel, startX));
      activeChannels[channel] = true;
      return;
    }
    // 5. Kein Platz → Figur vom anderen Rand umleiten
    let otherEdge = channel === 0 ? 2 : 0;
    for (let fig of figures) {
      if (fig.channel === otherEdge && fig.currentAlpha > 0.01) {
        fig.reassign(channel);
        activeChannels[channel] = true;
        return;
      }
    }
    // 6. Fallback: schwächste Figur ersetzen
    let weakestIdx = 0;
    for (let i = 1; i < figures.length; i++) {
      if (figures[i].currentAlpha < figures[weakestIdx].currentAlpha)
        weakestIdx = i;
    }
    figures[weakestIdx] = new Figure(channel, startX);
    activeChannels[channel] = true;
    return;
  }

  // ── Mittelkanal ────────────────────────────────────────────────────────────
  // Rand-Figuren (aktiv oder im Hold) werden zur Mitte gezogen.
  let highPri = [],
    lowPri = [];
  for (let i = 0; i < figures.length; i++) {
    let fig = figures[i];
    if (fig.channel === 1 || !fig.isActive()) continue; // nur Rand-Figuren
    if (activeChannels[fig.channel] && !(fig.targetX < 0 || fig.targetX > 1)) {
      highPri.push(i);
    } else if (!activeChannels[fig.channel] && fig.holdTimer > 0) {
      lowPri.push(i);
    }
  }
  let candidates = highPri.length > 0 && lowPri.length === 0 ? highPri : lowPri;

  if (candidates.length === 0) {
    // Keine Rand-Figuren → Mitte-Figur reaktivieren falls noch sichtbar
    for (let fig of figures) {
      if (fig.channel === 1 && fig.isActive()) {
        fig.targetAlpha = 1;
        fig.targetScale = 1;
        fig.holdTimer = 0;
        fig.targetX = CHANNEL_X[1];
        activeChannels[1] = true;
        return;
      }
    }
    // Fallback: neue Figur (sollte selten vorkommen)
    if (figures.length < MAX_FIGURES) {
      figures.push(new Figure(1, 0.5));
    }
    activeChannels[1] = true;
    return;
  }

  // Quellkanäle ermitteln
  let sourceChannels = new Set(candidates.map((i) => figures[i].channel));

  // Reduktion: alle Figuren am gleichen Randkanal
  let allSameEdge = sourceChannels.size === 1 && candidates.length > 1;
  let edgeChToKeep = -1;

  if (allSameEdge) {
    let srcCh = figures[candidates[0]].channel;
    let edgeStaysActive = activeChannels[srcCh];
    if (!edgeStaysActive) {
      // Randkanal wird deaktiviert: eine Figur rausschicken, Rest zur Mitte
      let exitFig = figures[candidates[0]];
      exitFig.holdTimer = DEACTIVATE_HOLD_FRAMES;
      exitFig.targetAlpha = 0;
      exitFig.targetX = srcCh === 0 ? -0.2 : 1.2;
      for (let k = 1; k < candidates.length; k++) {
        figures[candidates[k]].reassign(1);
      }
    } else {
      // Randkanal bleibt aktiv: eine Figur zur Mitte, eine am Rand behalten
      figures[candidates[1]].reassign(1);
      edgeChToKeep = srcCh;
    }
  } else {
    for (let idx of candidates) {
      figures[idx].reassign(1);
    }
  }

  // Randkanäle deaktivieren, außer er soll aktiv bleiben
  for (let srcCh of sourceChannels) {
    if (srcCh !== edgeChToKeep) activeChannels[srcCh] = false;
  }
  activeChannels[1] = true;
}

function handleChannelRelease(channel) {
  activeChannels[channel] = false;

  // Wenn Mitte losgelassen wird, aber ein Rand noch aktiv ist:
  // Mitte-Figur sofort zum aktiven Rand umleiten
  if (channel === 1) {
    let activeSide = -1;
    for (let ch = 0; ch < activeChannels.length; ch++) {
      if (activeChannels[ch] && ch !== 1) {
        activeSide = ch;
        break;
      }
    }
    if (activeSide >= 0) {
      for (let fig of figures) {
        if (fig.channel === 1 && fig.currentAlpha > 0.01) {
          fig.reassign(activeSide);
          return;
        }
      }
    }
  }

  // Nächsten erreichbaren aktiven Kanal suchen
  let nextChannel = -1;
  for (let ch = 0; ch < activeChannels.length; ch++) {
    if (activeChannels[ch] && (channel === 1 || ch === 1)) {
      nextChannel = ch;
      break;
    }
  }

  for (let fig of figures) {
    if (fig.channel === channel && nextChannel >= 0) {
      fig.reassign(nextChannel);
    } else if (fig.channel === channel) {
      fig.holdTimer = DEACTIVATE_HOLD_FRAMES;
      fig.targetAlpha = 0;
      if (channel === 0) fig.targetX = -0.2;
      else if (channel === 2) fig.targetX = 1.2;
    }
  }
}

function connectCsiInput() {
  if (typeof EventSource === "undefined") return;

  csiEventSource = new EventSource(CSI_EVENTS_URL);
  csiEventSource.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      return;
    }
    applyCsiChannels(data);
  };
  csiEventSource.onerror = () => {
    applyCsiChannelStates([false, false, false]);
  };
}

function applyCsiChannels(data) {
  const channels = data.channels || {};
  const states = data.states || null;
  if (states) {
    applyCsiChannelStates([
      Boolean(states.left),
      Boolean(states.center),
      Boolean(states.right),
    ]);
  } else {
    applyCsiChannelStates([
      Number(channels.left || 0) > CSI_CHANNEL_ON_THRESHOLD,
      Number(channels.center || 0) > CSI_CHANNEL_ON_THRESHOLD,
      Number(channels.right || 0) > CSI_CHANNEL_ON_THRESHOLD,
    ]);
  }
}

function applyCsiChannelStates(nextStates) {
  for (let channel = 0; channel < 3; channel++) {
    if (nextStates[channel] && !csiChannelStates[channel]) {
      handleChannelPress(channel);
    } else if (!nextStates[channel] && csiChannelStates[channel]) {
      handleChannelRelease(channel);
    }
  }
  csiChannelStates = nextStates.slice();
}

function keyPressed() {
  if (key === " ") {
    window.location.href = "examples/visualization/installation-visual.html";
    return false;
  }

  const channelMap = { a: 0, A: 0, s: 1, S: 1, d: 2, D: 2 };
  const channel = channelMap[key];
  if (channel === undefined) return;
  handleChannelPress(channel);
  return false;
}

function keyReleased() {
  const channelMap = { a: 0, A: 0, s: 1, S: 1, d: 2, D: 2 };
  const channel = channelMap[key];
  if (channel === undefined) return;
  handleChannelRelease(channel);
  return false;
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
  computeLayout();
}

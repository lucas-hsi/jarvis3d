// Cena 3D do clima (visual Aurora). Three.js r186 offline (frontend/vendor/three). Carregada pelo aurora.js só quando o
// servidor manda {"tipo":"cena","cena":"clima"} (ferramenta mostrar_clima, dados do wttr.in). Só desenha.
// export: mostrar(cidades), esconder(). Cidade = {nome, temp, cond(limpo|nublado|chuva|tempestade|neve|neblina), nuvem, noite, hora, descricao, max, min}
import * as THREE from 'three';

const cv = document.getElementById('au-w3d');
const labels = document.getElementById('au-wlabels');
const renderer = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
scene.add(new THREE.HemisphereLight(0xc8d6ff, 0x1a1040, 1.1));
const sunL = new THREE.DirectionalLight(0xffffff, 1.6); sunL.position.set(3, 7, 5); scene.add(sunL);
const flashL = new THREE.PointLight(0xcfe0ff, 0, 12, 1.6); scene.add(flashL);

// ---------- utilidades ----------
const TAU = Math.PI * 2, rnd = Math.random;
const spring = (t) => (t <= 0 ? 0 : 1 - Math.exp(-6.5 * t) * Math.cos(10.5 * t));
const easeIn = (t) => t * t * t;
const easeOut = (t) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
function glowTex(inner = 'rgba(255,255,255,1)', mid = 'rgba(255,255,255,.35)') {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, inner); gr.addColorStop(0.25, mid); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
const GLOW = glowTex();
function glow(color, size, opacity = 0.9) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
  s.scale.setScalar(size); return s;
}

// ---------- peças ----------
function platform(accent) {
  const g = new THREE.Group();
  const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.25, 1.32, 0.09, 72),
    new THREE.MeshStandardMaterial({ color: 0x161a3d, metalness: 0.35, roughness: 0.3, transparent: true, opacity: 0.78 }));
  g.add(disc);
  const rimMat = new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false });
  const rim = new THREE.Mesh(new THREE.TorusGeometry(1.28, 0.016, 8, 128), rimMat); rim.rotation.x = Math.PI / 2; rim.position.y = 0.05; g.add(rim);
  const inner = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.57, 96), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  inner.rotation.x = -Math.PI / 2; inner.position.y = 0.051; g.add(inner);
  const halo = glow(accent, 3.4, 0.22); halo.position.y = -0.1; g.add(halo);
  g.userData = { rimMat, inner };
  return g;
}
function cloud(color = 0xf3f6ff, n = 7, w = 1) {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.95, metalness: 0, transparent: true, opacity: 0.97 });
  for (let i = 0; i < n; i++) {
    const r = 0.22 + rnd() * 0.18;
    const m = new THREE.Mesh(new THREE.SphereGeometry(r, 28, 18), mat);
    m.position.set((i / (n - 1) - 0.5) * 0.95 * w, (Math.sin((i / (n - 1)) * Math.PI)) * 0.18 + rnd() * 0.05, (rnd() - 0.5) * 0.25);
    g.add(m);
  }
  g.scale.set(1, 0.82, 1);
  return g;
}
function sun() {
  const g = new THREE.Group();
  g.add(new THREE.Mesh(new THREE.SphereGeometry(0.4, 40, 24), new THREE.MeshBasicMaterial({ color: 0xffc95c })));
  g.add(glow(0xffa53a, 2.8, 0.85));
  const rays = new THREE.Group();
  const rm = new THREE.MeshBasicMaterial({ color: 0xffd27a, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false });
  for (let i = 0; i < 12; i++) {
    const r = new THREE.Mesh(new THREE.CapsuleGeometry(0.035, 0.2, 4, 8), rm);
    const a = (i / 12) * TAU; r.position.set(Math.cos(a) * 0.66, Math.sin(a) * 0.66, 0); r.rotation.z = a - Math.PI / 2; rays.add(r);
  }
  g.add(rays); g.userData.rays = rays; return g;
}
function moon() {
  const g = new THREE.Group();
  const c = document.createElement('canvas'); c.width = c.height = 256; const x = c.getContext('2d');
  x.fillStyle = '#e8ebff'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 40; i++) { x.fillStyle = `rgba(120,130,170,${0.08 + rnd() * 0.18})`; x.beginPath(); x.arc(rnd() * 256, rnd() * 256, 4 + rnd() * 18, 0, TAU); x.fill(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  g.add(new THREE.Mesh(new THREE.SphereGeometry(0.38, 40, 24), new THREE.MeshStandardMaterial({ map: t, emissive: 0x8088c0, emissiveIntensity: 0.55, roughness: 1 })));
  g.add(glow(0x9fb0ff, 2.2, 0.55));
  const sg = new THREE.BufferGeometry(), N = 90, p = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) { const a = rnd() * TAU, r = 0.7 + rnd() * 1.1; p[i * 3] = Math.cos(a) * r; p[i * 3 + 1] = (rnd() - 0.3) * 1.3; p[i * 3 + 2] = Math.sin(a) * r * 0.5 - 0.3; }
  sg.setAttribute('position', new THREE.BufferAttribute(p, 3));
  const stars = new THREE.Points(sg, new THREE.PointsMaterial({ size: 0.06, map: GLOW, color: 0xdfe6ff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  g.add(stars); g.userData.stars = stars; return g;
}
function rainSystem(accent, neve = false) {
  const N = neve ? 160 : 260, geo = neve ? new THREE.SphereGeometry(0.025, 6, 4) : new THREE.CylinderGeometry(0.007, 0.007, 0.17, 4);
  const mat = new THREE.MeshBasicMaterial({ color: neve ? 0xffffff : 0xa8d4ff, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false });
  const mesh = new THREE.InstancedMesh(geo, mat, N);
  const d = []; const M = new THREE.Matrix4();
  for (let i = 0; i < N; i++) d.push({ x: (rnd() - 0.5) * 1.3, z: (rnd() - 0.5) * 0.7, y: 0.1 + rnd() * 1.4, v: neve ? 0.5 + rnd() * 0.4 : 3 + rnd() * 1.5 });
  const splashes = [];
  const smat = () => new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
  const sgeo = new THREE.RingGeometry(0.03, 0.045, 24);
  const grp = new THREE.Group(); grp.add(mesh);
  for (let i = 0; i < 16; i++) { const s = new THREE.Mesh(sgeo, smat()); s.rotation.x = -Math.PI / 2; s.position.y = 0.06; s.userData.t = 9; grp.add(s); splashes.push(s); }
  let si = 0;
  grp.userData.update = (dt, k) => {
    for (let i = 0; i < N; i++) {
      const p = d[i]; p.y -= p.v * dt;
      if (p.y < 0.08) {
        if (!neve && rnd() < 0.18) { const s = splashes[si++ % splashes.length]; s.position.x = p.x; s.position.z = p.z; s.userData.t = 0; }
        p.y = 1.45 + rnd() * 0.2; p.x = (rnd() - 0.5) * 1.3; p.z = (rnd() - 0.5) * 0.7;
      }
      M.makeTranslation(p.x + (neve ? Math.sin(p.y * 4 + i) * 0.06 : 0), p.y, p.z); mesh.setMatrixAt(i, M);
    }
    mesh.instanceMatrix.needsUpdate = true; mat.opacity = 0.85 * k;
    for (const s of splashes) { s.userData.t += dt; const t = s.userData.t; const sc = 1 + t * 9; s.scale.set(sc, sc, sc); s.material.opacity = t < 0.5 ? (1 - t / 0.5) * 0.7 * k : 0; }
  };
  return grp;
}
function bolt() {
  const pts = []; let x = (rnd() - 0.5) * 0.4, y = 1.1;
  pts.push(new THREE.Vector3(x, y, 0.1));
  while (y > 0.1) { y -= 0.12 + rnd() * 0.1; x += (rnd() - 0.5) * 0.28; pts.push(new THREE.Vector3(x, Math.max(0.07, y), 0.1 + (rnd() - 0.5) * 0.1)); }
  return new THREE.BufferGeometry().setFromPoints(pts);
}

// ---------- montagem ----------
let root = null, items = [], t0 = 0, leaving = 0, running = false, active = false;
const lastTime = { t: performance.now() };

const DESC = { limpo: ['Céu limpo', 'Noite de céu limpo'], nublado: ['Nublado', 'Noite nublada'], chuva: ['Chuva', 'Chuva'], tempestade: ['Chuva e trovoadas', 'Chuva e trovoadas'], neve: ['Neve', 'Neve'], neblina: ['Neblina', 'Neblina'] };
const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function build(cidades) {
  root = new THREE.Group(); scene.add(root); items = [];
  const POS = cidades.length === 1 ? [[0, 0.1, 0]] : cidades.length === 2 ? [[-1.75, 0, 0.2], [1.75, 0, 0.2]] : [[-3.05, 0, 0.35], [0, 0.18, -0.8], [3.05, 0, 0.35]];
  cidades.slice(0, 3).forEach((c, i) => {
    const cond = DESC[c.cond] ? c.cond : 'limpo', noite = !!c.noite, molhado = cond === 'chuva' || cond === 'tempestade';
    const accent = molhado ? 0x7aa8ff : cond === 'neve' ? 0xdfe8ff : cond === 'nublado' || cond === 'neblina' ? 0x9aa6c8 : noite ? 0x9f8cff : 0xffb85c;
    const g = new THREE.Group(); g.position.set(...POS[i]); root.add(g);
    const pl = platform(accent); g.add(pl);
    const icon = new THREE.Group(); icon.position.y = 1.15; g.add(icon);
    const it = { g, pl, icon, accent, c, noite, delay: i * 0.2, base: POS[i][1] };
    if (molhado || cond === 'neve') {
      const cor = cond === 'neve' ? 0xb9c2dc : 0x7d86a8;
      const cl = cloud(cor, 8, 1.15); cl.position.y = 0.42; icon.add(cl);
      const cl2 = cloud(cond === 'neve' ? 0xd4daf0 : 0x9aa2c2, 6, 0.8); cl2.position.set(0.45, 0.62, -0.3); icon.add(cl2);
      const rain = rainSystem(accent, cond === 'neve'); rain.position.y = -1.15; icon.add(rain); it.rain = rain; it.clouds = [cl, cl2];
      if (cond === 'tempestade') {
        const lm = new THREE.LineBasicMaterial({ color: 0xe6eeff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending });
        const ln = new THREE.Line(bolt(), lm); ln.position.y = -1.15; icon.add(ln); it.bolt = ln; it.nextBolt = 1.5;
      }
    } else if (cond === 'nublado' || cond === 'neblina') {
      const astro = noite ? moon() : sun(); astro.position.set(-0.35, 0.45, -0.4); astro.scale.setScalar(0.7); icon.add(astro);
      if (noite) it.moon = astro; else it.sun = astro;
      const cl = cloud(cond === 'neblina' ? 0xa9b0c8 : 0xe3e8f6, 8, 1.15); cl.position.set(0.05, 0.12, 0.25); icon.add(cl);
      const cl2 = cloud(0xc6cde2, 6, 0.8); cl2.position.set(0.5, 0.35, -0.1); icon.add(cl2); it.clouds = [cl, cl2];
    } else if (noite) {
      const m = moon(); m.position.y = 0.25; icon.add(m); it.moon = m;
      if (c.nuvem) { const cl = cloud(0xb7bfe0, 5, 0.6); cl.scale.multiplyScalar(0.75); cl.position.set(0.5, -0.18, 0.45); icon.add(cl); it.clouds = [cl]; }
    } else {
      const s = sun(); s.position.y = 0.3; icon.add(s); it.sun = s;
      if (c.nuvem) { const cl = cloud(0xf6f8ff, 6, 0.85); cl.position.set(0.35, 0.02, 0.4); icon.add(cl); it.clouds = [cl]; }
    }
    const el = document.createElement('div'); el.className = 'au-wlab';
    const mm = c.max != null && c.min != null ? `máx ${esc(c.max)}° · mín ${esc(c.min)}°` : '';
    el.innerHTML = `<div class="wc">${esc(c.nome)}<span>${esc(c.hora || '')}</span></div><div class="wt"><b>0</b>°</div><div class="wd"></div><div class="wm">${mm}</div>`;
    el.querySelector('.wd').textContent = c.descricao || DESC[cond][noite ? 1 : 0];
    labels.appendChild(el); it.el = el; it.tb = el.querySelector('b');
    g.scale.setScalar(0.001);
    items.push(it);
  });
}
function clear() {
  if (root) { scene.remove(root); root.traverse((o) => { o.geometry?.dispose?.(); if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose()); }); }
  root = null; items = []; labels.innerHTML = '';
}

function resize() {
  const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); cv.style.width = w + 'px'; cv.style.height = h + 'px';
  cam.aspect = w / h; cam.updateProjectionMatrix();
}
addEventListener('resize', resize); resize();

const v3 = new THREE.Vector3();
let mx = 0, my = 0;
addEventListener('pointermove', (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; });

function frame(now) {
  if (!running) return;
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (now - lastTime.t) / 1000); lastTime.t = now;
  const t = (now - t0) / 1000, amp = window.__amp || 0;
  // câmera: entra de longe (dolly) e fica balançando de leve
  const largura = items.length >= 3 ? 5.8 : items.length === 2 ? 4.2 : 2.8;                 // cabe tudo, com folga para o balanço da câmera
  const fit = Math.max(items.length >= 3 ? 9.4 : 8, largura / (Math.tan((19 * Math.PI) / 180) * cam.aspect));
  const e = easeOut(t / 1.8), out = leaving ? easeIn(Math.min(1, (now - leaving) / 900)) : 0;
  const dist = fit + (1 - e) * 6 + out * 3;
  const orb = Math.sin(t * 0.18) * 0.32 + mx * 0.35;
  cam.position.set(Math.sin(orb) * dist, 2.3 + (1 - e) * 2 - my * 0.8, Math.cos(orb) * dist);
  cam.fov = 38 + (1 - e) * 10; cam.updateProjectionMatrix();
  cam.lookAt(0, -0.35, 0);
  let flash = 0;
  for (const it of items) {
    const lt = t - it.delay, s = leaving ? Math.max(0.001, 1 - easeIn(Math.min(1, (now - leaving) / 700 - it.delay * 0.5))) : Math.max(0.001, spring(lt));
    it.g.scale.setScalar(s);
    it.g.position.y = it.base + (1 - Math.min(1, spring(lt))) * -1.6 + Math.sin(t * 0.9 + it.delay * 7) * 0.06;
    it.icon.rotation.y = Math.sin(t * 0.4 + it.delay * 3) * 0.25;
    it.icon.scale.setScalar(1 + amp * 0.06);
    it.pl.userData.rimMat.opacity = 0.55 + amp * 0.45 + Math.sin(t * 2 + it.delay * 9) * 0.1;
    it.pl.userData.inner.rotation.z += dt * 0.3;
    if (it.sun) { it.sun.userData.rays.rotation.z += dt * 0.35; const p = 1 + Math.sin(t * 2.2) * 0.05; it.sun.userData.rays.scale.set(p, p, p); }
    if (it.moon) { it.moon.userData.stars.material.opacity = 0.6 + Math.sin(t * 3.1) * 0.3; it.moon.userData.stars.rotation.y += dt * 0.05; }
    if (it.clouds) it.clouds.forEach((c, j) => { c.position.x += Math.sin(t * 0.5 + j * 2) * dt * 0.08; });
    if (it.rain) it.rain.userData.update(dt, Math.min(1, Math.max(0, lt - 0.6)) * (leaving ? 1 - out : 1));
    if (it.bolt) {
      it.nextBolt -= dt;
      if (it.nextBolt < 0 && !leaving) { it.bolt.geometry.dispose(); it.bolt.geometry = bolt(); it.boltT = 0; it.nextBolt = 1.8 + rnd() * 2.6; }
      if (it.boltT !== undefined) { it.boltT += dt; const f = it.boltT < 0.22 ? (Math.sin(it.boltT * 90) > -0.3 ? 1 : 0.2) * (1 - it.boltT / 0.22) : 0; it.bolt.material.opacity = f; if (f > flash) { flash = f; it.g.getWorldPosition(flashL.position); flashL.position.y += 1.3; } }
    }
    // rótulo: projeta a base da plataforma na tela
    it.g.getWorldPosition(v3); v3.y -= 0.35; v3.project(cam);
    const x = (v3.x * 0.5 + 0.5) * innerWidth, y = (-v3.y * 0.5 + 0.5) * innerHeight;
    it.el.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) translate(-50%,0)`;
    const a = leaving ? 1 - out : Math.min(1, Math.max(0, (lt - 0.4) * 2)); it.el.style.opacity = a;
    it.tb.textContent = Math.round((+it.c.temp || 0) * easeOut((lt - 0.4) / 1.4));
  }
  flashL.intensity = flash * 40;
  document.body.classList.toggle('au-raio', flash > 0.6);
  renderer.render(scene, cam);
  if (leaving && now - leaving > 1300) { running = false; active = false; clear(); cv.classList.remove('on'); renderer.clear(); }
}

export function mostrar(cidades) {
  clear(); build(cidades); t0 = performance.now(); leaving = 0; active = true; cv.classList.add('on');
  if (!running) { running = true; lastTime.t = performance.now(); requestAnimationFrame(frame); }
}
export function esconder() { if (active && !leaving) leaving = performance.now(); document.body.classList.remove('au-raio'); }
export const ativo = () => active;

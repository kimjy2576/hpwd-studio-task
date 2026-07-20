const { useState, useMemo, useRef, useEffect } = React;

// ── AppSwitcher (탭 네비게이션) ──
function AppSwitcher({ current }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);
  const apps = [
    { id: 'studio', label: 'HPWD Studio', desc: '시뮬 캔버스', href: '/' },
    { id: 'cycle-runner', label: 'Cycle Runner', desc: '사이클 조합·실행', href: '/cycle-runner/' },
    { id: 'component-studio', label: 'Component Studio', desc: '컴포넌트 작성', href: '/component-studio/' },
    { id: 'on-design-studio', label: 'On-Design Studio', desc: '냉매 부품 설계', href: '/on-design-studio/' },
    { id: 'air-on-design', label: 'Air On-Design', desc: '공기 부품 설계', href: '/air-on-design/' },
    { id: 'calibration-studio', label: 'Calibration Studio', desc: 'Calibration & Validation', href: '/calibration-studio/' },
    { id: 'model-docs', label: 'Model Docs', desc: '수학적 모델링 문서', href: '/model-docs/' },
  ];
  const active = apps.find(a => a.id === current) || apps[0];
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-100 transition-colors">
        <div className="w-2 h-2 rounded-sm bg-teal-600 shrink-0" />
        <span className="font-bold text-slate-900 tracking-wide text-[11px]">{active.label}</span>
        <span className="text-slate-400 text-[9px]">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-lg shadow-xl w-56 p-1">
          {apps.map(a => {
            const isA = a.id === current;
            return (
              <button key={a.id} onClick={() => { if (!isA) window.location.href = a.href; }}
                className={`w-full text-left px-2.5 py-1.5 rounded flex items-start gap-2 ${isA ? 'bg-teal-50 cursor-default' : 'hover:bg-slate-50'}`}>
                <span className={`mt-0.5 w-3 text-center text-[11px] ${isA ? 'text-teal-700' : 'text-slate-300'}`}>{isA ? '●' : '○'}</span>
                <div className="flex-1 min-w-0">
                  <div className={`font-semibold text-[12px] ${isA ? 'text-teal-900' : 'text-slate-800'}`}>{a.label}</div>
                  <div className="text-[10px] text-slate-500">{a.desc}</div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Slider (On-Design Studio 벤치마크: 슬라이더 + 편집가능 숫자) ──
function Slider({ label, sublabel, value, min, max, step, onChange, color = 'teal', decimals = 1 }) {
  const pct = ((value - min) / (max - min)) * 100;
  const colorMap = {
    teal: { fill: '#0d9488', text: 'text-teal-700' },
    blue: { fill: '#2563eb', text: 'text-blue-700' },
    amber: { fill: '#d97706', text: 'text-amber-700' },
    purple: { fill: '#7c3aed', text: 'text-purple-700' },
    cyan: { fill: '#0891b2', text: 'text-cyan-700' },
    green: { fill: '#059669', text: 'text-green-700' },
  };
  const c = colorMap[color] || colorMap.teal;
  const [editing, setEditing] = useState(null);
  useEffect(() => { setEditing(null); }, [value]);
  const displayValue = editing !== null ? editing : Number(value).toFixed(decimals);
  const commit = () => {
    if (editing === null) return;
    const t = editing.trim();
    if (t === '' || t === '-' || t === '.') { setEditing(null); return; }
    const parsed = parseFloat(t);
    if (isNaN(parsed)) { setEditing(null); return; }
    onChange(Math.max(min, Math.min(max, parsed)));
  };
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-baseline gap-1">
          <span className="text-[12px] font-semibold text-slate-700">{label}</span>
          {sublabel && <span className="text-[10px] text-slate-400 mono">{sublabel}</span>}
        </div>
        <input type="text" inputMode="decimal" value={displayValue}
          onChange={(e) => setEditing(e.target.value)}
          onFocus={(e) => { setEditing(Number(value).toFixed(decimals)); e.target.select(); }}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); if (e.key === 'Escape') { setEditing(null); e.target.blur(); } }}
          className={`w-20 text-right text-[12px] mono font-semibold ${c.text} bg-transparent border border-transparent outline-none px-1 py-0.5 rounded hover:bg-slate-50 focus:bg-white focus:border-slate-300`} />
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer slider-thumb"
        style={{ background: `linear-gradient(to right, ${c.fill} ${pct}%, #e2e8f0 ${pct}%)` }} />
    </div>
  );
}

// ── 부품 선택 탭 ──
const AIR_PARTS = [
  { key: 'fan', label: '팬', en: 'Centrifugal Fan', icon: '🌀', color: 'teal' },
  { key: 'drum', label: '드럼', en: 'Tumbling Drum', icon: '🛢', color: 'blue' },
  { key: 'filter', label: '필터', en: 'Porous Filter', icon: '▦', color: 'amber' },
];

// ═══════════════════════════════════════════
// 팬 도면 (원심팬 단면도 — SVG)
// ═══════════════════════════════════════════
function FanSchematic({ p }) {
  // 스케일: mm → px (뷰 300x300 중심)
  const cx = 160, cy = 160;
  const scale = 0.6;
  const rD1 = (p.D1 / 2) * scale;  // 입구 반경
  const rD2 = (p.D2 / 2) * scale;  // 출구 반경
  // 블레이드 (Z개, beta 각도)
  const blades = [];
  for (let i = 0; i < p.Z; i++) {
    const ang = (i / p.Z) * 2 * Math.PI;
    const x1 = cx + rD1 * Math.cos(ang);
    const y1 = cy + rD1 * Math.sin(ang);
    // 블레이드 후향 (beta2)
    const angOut = ang + (p.beta2 - 90) * Math.PI / 180 * 0.3;
    const x2 = cx + rD2 * Math.cos(angOut);
    const y2 = cy + rD2 * Math.sin(angOut);
    blades.push(
      <path key={i} d={`M ${x1.toFixed(1)} ${y1.toFixed(1)} Q ${((x1 + x2) / 2 + (y2 - y1) * 0.2).toFixed(1)} ${((y1 + y2) / 2 - (x2 - x1) * 0.2).toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`}
        stroke="#0d9488" strokeWidth="2" fill="none" strokeLinecap="round" opacity="0.85" />
    );
  }
  return (
    <svg viewBox="0 0 320 320" className="w-full h-full">
      {/* 스크롤 하우징 (근사 나선) */}
      <circle cx={cx} cy={cy} r={rD2 + 18 + p.cutoffGap * scale} fill="#f0fdfa" stroke="#99f6e4" strokeWidth="1.5" strokeDasharray="4 3" />
      {/* 출구 원 (D2) */}
      <circle cx={cx} cy={cy} r={rD2} fill="none" stroke="#14b8a6" strokeWidth="1.5" opacity="0.5" />
      {/* 입구 원 (D1) */}
      <circle cx={cx} cy={cy} r={rD1} fill="#ccfbf1" stroke="#0d9488" strokeWidth="1.5" />
      {/* 블레이드 */}
      {blades}
      {/* 허브 */}
      <circle cx={cx} cy={cy} r="6" fill="#0f766e" />
      {/* 치수선 D2 */}
      <line x1={cx} y1={cy} x2={cx + rD2} y2={cy} stroke="#64748b" strokeWidth="0.8" strokeDasharray="2 2" />
      <text x={cx + rD2 / 2} y={cy - 4} fontSize="9" fill="#0d9488" className="mono" textAnchor="middle">D2={p.D2}</text>
      {/* 치수선 D1 */}
      <text x={cx} y={cy - rD1 - 4} fontSize="9" fill="#0f766e" className="mono" textAnchor="middle">D1={p.D1}</text>
      {/* 라벨 */}
      <text x="10" y="16" fontSize="10" fill="#475569" className="mono">Z={p.Z} blades · β2={p.beta2}°</text>
      <text x="10" y="310" fontSize="9" fill="#94a3b8" className="mono">원심팬 정면 단면 (스크롤 하우징 점선)</text>
    </svg>
  );
}

// ═══════════════════════════════════════════
// 드럼 도면 (드럼 단면 + 포 + 텀블링)
// ═══════════════════════════════════════════
function DrumSchematic({ p }) {
  const cx = 160, cy = 150;
  const R = 110;
  const fillH = R * 2 * (p.fill_frac || 0.4);  // 포 채움 높이
  return (
    <svg viewBox="0 0 320 320" className="w-full h-full">
      {/* 드럼 외벽 */}
      <circle cx={cx} cy={cy} r={R} fill="#eff6ff" stroke="#3b82f6" strokeWidth="2.5" />
      {/* 리프터 (배플, 3개) */}
      {[0, 120, 240].map(a => {
        const rad = a * Math.PI / 180;
        const x1 = cx + (R - 2) * Math.cos(rad), y1 = cy + (R - 2) * Math.sin(rad);
        const x2 = cx + (R - 20) * Math.cos(rad), y2 = cy + (R - 20) * Math.sin(rad);
        return <line key={a} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#2563eb" strokeWidth="3" strokeLinecap="round" />;
      })}
      {/* 포 (하단 채움, 텀블링) */}
      <path d={`M ${cx - R * 0.9} ${cy + R - fillH} Q ${cx} ${cy + R - fillH + 20} ${cx + R * 0.9} ${cy + R - fillH} L ${cx + R * 0.7} ${cy + R * 0.7} Q ${cx} ${cy + R} ${cx - R * 0.7} ${cy + R * 0.7} Z`}
        fill="#93c5fd" opacity="0.6" />
      {/* 회전 화살표 */}
      <path d={`M ${cx + R + 8} ${cy} A ${R + 8} ${R + 8} 0 0 1 ${cx} ${cy + R + 8}`} fill="none" stroke="#1d4ed8" strokeWidth="1.5" markerEnd="url(#arrow)" opacity="0.6" />
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8" fill="#1d4ed8" opacity="0.6" />
        </marker>
      </defs>
      {/* 중심축 */}
      <circle cx={cx} cy={cy} r="5" fill="#1e40af" />
      {/* 라벨 */}
      <text x="10" y="16" fontSize="10" fill="#475569" className="mono">포 {p.M_dry}kg · {p.fabric} · {p.RPM}rpm</text>
      <text x={cx} y={cy - R - 6} fontSize="9" fill="#2563eb" className="mono" textAnchor="middle">⌀ drum · Fr 텀블링</text>
      <text x="10" y="310" fontSize="9" fill="#94a3b8" className="mono">드럼 정면 (리프터 3 · 포 텀블링)</text>
    </svg>
  );
}

// ═══════════════════════════════════════════
// 필터 도면 (다공 매질 단면)
// ═══════════════════════════════════════════
function FilterSchematic({ p }) {
  const x0 = 60, y0 = 70, w = 200, h = 180;
  const th = (p.thickness || 10) * 3;  // 두께 시각화
  return (
    <svg viewBox="0 0 320 320" className="w-full h-full">
      {/* 프레임 */}
      <rect x={x0} y={y0} width={w} height={h} fill="#fffbeb" stroke="#d97706" strokeWidth="2" rx="4" />
      {/* 다공 매질 (격자 패턴) */}
      {Array.from({ length: 8 }).map((_, i) =>
        Array.from({ length: 7 }).map((_, j) => (
          <circle key={`${i}-${j}`} cx={x0 + 20 + i * 22} cy={y0 + 20 + j * 22} r="4"
            fill="none" stroke="#f59e0b" strokeWidth="1" opacity="0.5" />
        ))
      )}
      {/* 공기 흐름 화살표 */}
      {[0, 1, 2].map(i => (
        <g key={i}>
          <line x1={x0 - 40} y1={y0 + 40 + i * 50} x2={x0 - 8} y2={y0 + 40 + i * 50} stroke="#0891b2" strokeWidth="2" markerEnd="url(#fArrow)" />
          <line x1={x0 + w + 8} y1={y0 + 40 + i * 50} x2={x0 + w + 40} y2={y0 + 40 + i * 50} stroke="#0891b2" strokeWidth="1.5" strokeDasharray="3 2" markerEnd="url(#fArrow)" opacity="0.5" />
        </g>
      ))}
      <defs>
        <marker id="fArrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8" fill="#0891b2" />
        </marker>
      </defs>
      {/* 치수 */}
      <text x={x0 + w / 2} y={y0 - 8} fontSize="9" fill="#d97706" className="mono" textAnchor="middle">면적 {p.area}m² · 두께 {p.thickness}mm</text>
      <text x="10" y="16" fontSize="10" fill="#475569" className="mono">다공도 ε={p.porosity} · {p.media}</text>
      <text x="10" y="310" fontSize="9" fill="#94a3b8" className="mono">필터 단면 (공기 관통 · Ergun 압력강하)</text>
    </svg>
  );
}

// ── 부품별 설계변수 사이드바 ──
function FanControls({ p, set }) {
  return (
    <div>
      <SectionLabel>임펠러</SectionLabel>
      <Slider label="D1" sublabel="[mm] 입구경" value={p.D1} min={50} max={250} step={1} decimals={0} color="teal" onChange={v => set('D1', v)} />
      <Slider label="D2" sublabel="[mm] 출구경" value={p.D2} min={80} max={350} step={1} decimals={0} color="teal" onChange={v => set('D2', v)} />
      <Slider label="b1" sublabel="[mm] 입구폭" value={p.b1} min={10} max={120} step={1} decimals={0} color="teal" onChange={v => set('b1', v)} />
      <Slider label="b2" sublabel="[mm] 출구폭" value={p.b2} min={10} max={120} step={1} decimals={0} color="teal" onChange={v => set('b2', v)} />
      <Slider label="β1" sublabel="[°] 입구각" value={p.beta1} min={10} max={80} step={1} decimals={0} color="cyan" onChange={v => set('beta1', v)} />
      <Slider label="β2" sublabel="[°] 출구각" value={p.beta2} min={90} max={170} step={1} decimals={0} color="cyan" onChange={v => set('beta2', v)} />
      <Slider label="Z" sublabel="블레이드 수" value={p.Z} min={8} max={60} step={1} decimals={0} color="cyan" onChange={v => set('Z', v)} />
      <SectionLabel>스크롤</SectionLabel>
      <Slider label="cutoffGap" sublabel="[mm]" value={p.cutoffGap} min={2} max={30} step={0.5} decimals={1} color="purple" onChange={v => set('cutoffGap', v)} />
      <Slider label="wrapAngle" sublabel="[°]" value={p.wrapAngle} min={180} max={400} step={5} decimals={0} color="purple" onChange={v => set('wrapAngle', v)} />
    </div>
  );
}

function DrumControls({ p, set }) {
  return (
    <div>
      <SectionLabel>드럼 형상</SectionLabel>
      <Slider label="포 무게" sublabel="[kg] M_dry" value={p.M_dry} min={0.5} max={12} step={0.1} decimals={1} color="blue" onChange={v => set('M_dry', v)} />
      <Slider label="채움율" sublabel="fill" value={p.fill_frac} min={0.1} max={0.8} step={0.05} decimals={2} color="blue" onChange={v => set('fill_frac', v)} />
      <Slider label="RPM" sublabel="[rpm] 회전" value={p.RPM} min={0} max={120} step={1} decimals={0} color="blue" onChange={v => set('RPM', v)} />
      <SectionLabel>열전달</SectionLabel>
      <Slider label="A_eff" sublabel="[m²] 증발면적" value={p.A_eff} min={1} max={30} step={0.5} decimals={1} color="cyan" onChange={v => set('A_eff', v)} />
      <Slider label="h_a" sublabel="[W/m²K]" value={p.h_a} min={10} max={150} step={5} decimals={0} color="cyan" onChange={v => set('h_a', v)} />
    </div>
  );
}

function FilterControls({ p, set }) {
  return (
    <div>
      <SectionLabel>필터 형상</SectionLabel>
      <Slider label="면적" sublabel="[m²]" value={p.area} min={0.005} max={0.1} step={0.005} decimals={3} color="amber" onChange={v => set('area', v)} />
      <Slider label="두께" sublabel="[mm]" value={p.thickness} min={1} max={50} step={1} decimals={0} color="amber" onChange={v => set('thickness', v)} />
      <SectionLabel>다공 매질</SectionLabel>
      <Slider label="다공도" sublabel="ε" value={p.porosity} min={0.3} max={0.98} step={0.01} decimals={2} color="green" onChange={v => set('porosity', v)} />
    </div>
  );
}

function SectionLabel({ children }) {
  return <div className="mono text-[10px] font-semibold text-slate-400 uppercase tracking-wide mt-4 mb-2 first:mt-0">{children}</div>;
}

// ── 메인 앱 ──
function AirOnDesign() {
  const [part, setPart] = useState('fan');
  const [fanP, setFanP] = useState({ D1: 120, D2: 175, b1: 60, b2: 50, beta1: 30, beta2: 145, Z: 36, cutoffGap: 8, wrapAngle: 360 });
  const [drumP, setDrumP] = useState({ M_dry: 3.0, fill_frac: 0.4, RPM: 45, A_eff: 10, h_a: 50, fabric: 'cotton' });
  const [filterP, setFilterP] = useState({ area: 0.0136, thickness: 10, porosity: 0.9, media: 'nonwoven' });

  const setFan = (k, v) => setFanP({ ...fanP, [k]: v });
  const setDrum = (k, v) => setDrumP({ ...drumP, [k]: v });
  const setFilter = (k, v) => setFilterP({ ...filterP, [k]: v });

  const partMeta = AIR_PARTS.find(x => x.key === part);

  return (
    <div className="min-h-screen">
      {/* 탭 네비게이션 */}
      <div className="bg-white border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 py-1.5"><AppSwitcher current="air-on-design" /></div>
      </div>
      {/* 헤더 */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-blue-500 flex items-center justify-center text-white font-bold">◈</div>
            <div>
              <h1 className="text-base font-bold text-slate-800">Air On-Design</h1>
              <p className="mono text-[10px] text-slate-400">공기 부품 설계 — 팬·드럼·필터 형상</p>
            </div>
          </div>
          <button className="bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold px-4 py-2 rounded-lg">
            설계 동기화
          </button>
        </div>
      </header>

      {/* 부품 선택 탭 */}
      <div className="max-w-6xl mx-auto px-6 pt-5">
        <div className="flex gap-2">
          {AIR_PARTS.map(pt => (
            <button key={pt.key} onClick={() => setPart(pt.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl border-2 transition-all ${part === pt.key ? 'bg-white shadow-sm' : 'border-transparent bg-slate-100 hover:bg-slate-50'}`}
              style={part === pt.key ? { borderColor: `var(--${pt.color === 'teal' ? 'accent' : pt.color})` } : {}}>
              <span className="text-lg">{pt.icon}</span>
              <div className="text-left">
                <div className="text-sm font-bold text-slate-800">{pt.label}</div>
                <div className="mono text-[9px] text-slate-400">{pt.en}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 사이드바(설계변수) + 메인(도면) */}
      <main className="max-w-6xl mx-auto px-6 py-5 grid grid-cols-[320px_1fr] gap-5">
        {/* 사이드바 — 설계변수 */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <h3 className="text-sm font-bold text-slate-700 mb-4">설계 변수 · {partMeta.label}</h3>
          {part === 'fan' && <FanControls p={fanP} set={setFan} />}
          {part === 'drum' && <DrumControls p={drumP} set={setDrum} />}
          {part === 'filter' && <FilterControls p={filterP} set={setFilter} />}
        </div>

        {/* 메인 — 도면 */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-700">형상 도면</h3>
            <span className="mono text-[10px] text-slate-400">2D 단면 · 설계변수 반영</span>
          </div>
          <div className="flex-1 flex items-center justify-center bg-slate-50 rounded-xl min-h-[360px]">
            <div className="w-full max-w-[420px] aspect-square">
              {part === 'fan' && <FanSchematic p={fanP} />}
              {part === 'drum' && <DrumSchematic p={drumP} />}
              {part === 'filter' && <FilterSchematic p={filterP} />}
            </div>
          </div>
          <p className="mono text-[10px] text-slate-400 mt-3 text-center">
            설계 변수를 조절하면 도면이 실시간 반영됩니다 · 백엔드 검증 로직 연동 예정
          </p>
        </div>
      </main>

      <footer className="max-w-6xl mx-auto px-6 py-4 text-center">
        <p className="mono text-[10px] text-slate-300">
          UI 프로토타입 · 냉매 On-Design Studio 벤치마크 · 공기 컴포넌트 백엔드 로직 완비(fan/drum/filter L1-L3)
        </p>
      </footer>
    </div>
  );
}

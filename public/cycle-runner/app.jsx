const { useState, useMemo, useRef, useEffect } = React;

// ── AppSwitcher (좌측 상단 탭 네비게이션 — 다른 스튜디오로 이동) ──
function AppSwitcher({ current }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);
  const apps = [
    { id: 'studio',            label: 'HPWD Studio',       desc: '시뮬 캔버스',   href: '/' },
    { id: 'cycle-runner',      label: 'Cycle Runner',      desc: '사이클 조합·실행', href: '/cycle-runner/' },
    { id: 'component-studio',  label: 'Component Studio',  desc: '컴포넌트 작성', href: '/component-studio/' },
    { id: 'calibration-studio', label: 'Calibration Studio', desc: 'Calibration & Validation', href: '/calibration-studio/' },
    { id: 'on-design-studio',  label: 'On-Design Studio',  desc: 'On-design 모델 설계', href: '/on-design-studio/' },
    { id: 'model-docs',        label: 'Model Docs',        desc: '수학적 모델링 문서', href: '/model-docs/' },
  ];
  const active = apps.find(a => a.id === current) || apps[0];
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-100 transition-colors">
        <div className="w-2 h-2 rounded-sm bg-blue-600 shrink-0"></div>
        <span className="font-bold text-slate-900 tracking-wide text-sm">{active.label}</span>
        <span className="text-slate-400 text-[10px]">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-lg shadow-xl w-60 p-1">
          {apps.map(a => {
            const isActive = a.id === current;
            return (
              <button key={a.id}
                onClick={() => { if (!isActive) window.location.href = a.href; }}
                className={`w-full text-left px-2.5 py-1.5 rounded flex items-start gap-2 transition-colors ${isActive ? 'bg-blue-50 cursor-default' : 'hover:bg-slate-50'}`}>
                <span className={`mt-0.5 w-3 text-center text-[11px] ${isActive ? 'text-blue-700' : 'text-slate-300'}`}>{isActive ? '●' : '○'}</span>
                <div className="flex-1 min-w-0">
                  <div className={`font-semibold text-[12px] ${isActive ? 'text-blue-900' : 'text-slate-800'}`}>{a.label}</div>
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

// ── 설계변수 패널 (컴포넌트 클릭 시 fidelity별 변수 편집) ──
// 백엔드 modelDescription 메타 (window.COMPONENT_PARAM_META) 사용.
function ParamPanel({ comp, compLabel, fidelity, values, onChange, onClose }) {
  const META = (typeof window !== 'undefined' && window.COMPONENT_PARAM_META) || {};
  const params = (META[comp] && META[comp][String(fidelity)]) || [];

  // group별 분류 (Material/Operating/Geometry/Fitting/General)
  const byGroup = {};
  params.forEach(p => {
    const g = p.group || 'General';
    (byGroup[g] = byGroup[g] || []).push(p);
  });
  const groupOrder = ['Material', 'Operating', 'Geometry', 'Fitting', 'General'];
  const groups = Object.keys(byGroup).sort((a, b) => {
    const ia = groupOrder.indexOf(a), ib = groupOrder.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });

  const isL3 = fidelity === 3;
  const val = (name, def) => (values && name in values) ? values[name] : def;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <h3 className="text-base font-bold text-slate-800">{compLabel} 설계변수</h3>
            <p className="mono text-[11px] text-slate-400">L{fidelity} · {params.length}개 파라미터</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
        </div>

        {/* L3 안내 (형상 → On-Design Studio) */}
        {isL3 && (
          <div className="mx-5 mt-3 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between">
            <span className="text-[11px] text-blue-700">L3 상세 형상은 On-Design Studio에서 도면으로 설계</span>
            <a href={`/on-design-studio/?part=${comp}`} className="mono text-[11px] font-semibold text-blue-600 hover:underline shrink-0 ml-2">열기 →</a>
          </div>
        )}

        {/* 변수 목록 (group별) */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {params.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">이 fidelity는 설계변수가 없습니다</p>
          )}
          {groups.map(g => (
            <div key={g} className="mb-4">
              <div className="mono text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">{g}</div>
              <div className="space-y-2">
                {byGroup[g].map(p => (
                  <ParamRow key={p.name} p={p} value={val(p.name, p.start)}
                    onChange={v => onChange(p.name, v)} />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* 푸터 */}
        <div className="px-5 py-3 border-t border-slate-100 flex justify-end gap-2">
          <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700 px-4 py-2">닫기</button>
        </div>
      </div>
    </div>
  );
}

function ParamRow({ p, value, onChange }) {
  const isString = p.type === 'String' || typeof p.start === 'string';
  const hasOptions = Array.isArray(p.options) && p.options.length > 0;
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="mono text-[12px] font-semibold text-slate-700">{p.name}</span>
          {p.unit && p.unit !== '-' && <span className="mono text-[10px] text-slate-400">[{p.unit}]</span>}
        </div>
        {p.desc && <div className="text-[10px] text-slate-400 truncate">{p.desc}</div>}
      </div>
      {hasOptions ? (
        <select value={value} onChange={e => onChange(e.target.value)}
          className="mono text-[12px] border border-slate-200 rounded px-2 py-1 bg-white w-32 shrink-0 focus:border-blue-400 focus:outline-none">
          {p.options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : isString ? (
        <input type="text" value={value} onChange={e => onChange(e.target.value)}
          className="mono text-[12px] text-right border border-slate-200 rounded px-2 py-1 w-32 shrink-0 focus:border-blue-400 focus:outline-none" />
      ) : (
        <input type="number" value={value} onChange={e => onChange(parseFloat(e.target.value))}
          className="mono text-[12px] text-right border border-slate-200 rounded px-2 py-1 w-28 shrink-0 focus:border-blue-400 focus:outline-none" />
      )}
    </div>
  );
}

// ── 컴포넌트 정의 (냉매 4 + 공기 3) ──
const REF_COMPONENTS = [
  { key: 'compressor', label: '압축기', en: 'Compressor', color: 'var(--comp)', icon: '⊙' },
  { key: 'condenser',  label: '응축기', en: 'Condenser',  color: 'var(--cond)', icon: '▤' },
  { key: 'eev',        label: '팽창밸브', en: 'EEV',       color: 'var(--eev)',  icon: '◇' },
  { key: 'evaporator', label: '증발기', en: 'Evaporator', color: 'var(--evap)', icon: '▤' },
];

const AIR_CORE = [
  { key: 'drum',       label: '드럼',   en: 'Drum' },
  { key: 'filter',     label: '필터',   en: 'Filter' },
  { key: 'evaporator', label: '증발기', en: 'Evaporator' },
  { key: 'condenser',  label: '응축기', en: 'Condenser' },
];

const FIDELITY = [
  { v: 1, label: 'L1', desc: 'off-design (상수/UA)' },
  { v: 2, label: 'L2', desc: 'moving-boundary' },
  { v: 3, label: 'L3', desc: 'on-design (셀별)' },
];

// fidelity 세그먼트 색상
const fidColor = (v) => ({ 1: '#64748b', 2: '#0891b2', 3: '#2563eb' }[v]);

// ── fidelity 세그먼트 선택기 ──
function FidelitySelector({ value, onChange }) {
  return (
    <div className="inline-flex rounded-lg bg-slate-100 p-0.5">
      {FIDELITY.map(f => (
        <button
          key={f.v}
          onClick={() => onChange(f.v)}
          title={f.desc}
          className={`fid-seg mono text-xs font-semibold px-2.5 py-1 rounded-md ${value === f.v ? 'on' : 'text-slate-500 hover:text-slate-700'}`}
          style={value === f.v ? { background: fidColor(f.v) } : {}}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}

// ── 냉매 사이클 다이어그램 (2×2 배치, 순환 화살표) ──
function RefrigerantCycle({ fidelity, setFid, running, onEditParams }) {
  // 배치: 압축기(좌하) → 응축기(좌상) → EEV(우상) → 증발기(우하) → 압축기
  const positions = {
    compressor: { row: 2, col: 1 },
    condenser:  { row: 1, col: 1 },
    eev:        { row: 1, col: 2 },
    evaporator: { row: 2, col: 2 },
  };
  return (
    <div className="relative bg-white rounded-2xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-slate-700">냉매 루프</h3>
        <span className="mono text-[11px] text-slate-400">압축기 → 응축기 → 팽창밸브 → 증발기 (고정)</span>
      </div>
      <div className="grid grid-cols-2 gap-x-16 gap-y-6 relative">
        {REF_COMPONENTS.map(c => (
          <div
            key={c.key}
            className="node bg-white rounded-xl border-2 p-3.5"
            style={{ borderColor: c.color, gridRow: positions[c.key].row, gridColumn: positions[c.key].col }}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg" style={{ color: c.color }}>{c.icon}</span>
              <div className="flex-1">
                <div className="text-sm font-bold text-slate-800">{c.label}</div>
                <div className="mono text-[10px] text-slate-400">{c.en}</div>
              </div>
              <button onClick={() => onEditParams(c.key)} title="설계변수 편집"
                className="text-slate-300 hover:text-slate-600 text-sm px-1" style={{ color: c.color }}>⚙</button>
            </div>
            <FidelitySelector value={fidelity[c.key]} onChange={v => setFid(c.key, v)} />
          </div>
        ))}
      </div>
      {/* 순환 방향 표시 */}
      <div className="flex justify-center mt-4">
        <span className={`mono text-[11px] px-2 py-0.5 rounded ${running ? 'bg-blue-50 text-blue-600' : 'bg-slate-50 text-slate-400'}`}>
          {running ? '⟳ 냉매 순환 중' : '⟳ 순환 (정지)'}
        </span>
      </div>
    </div>
  );
}

// ── 공기 경로 (팬 삽입 가능) ──
function AirPath({ fidelity, setFid, fanPosition, setFanPosition, running, onEditParams }) {
  // 팬 슬롯: 각 코어 컴포넌트 사이 + 양끝 (0 ~ AIR_CORE.length)
  const slots = [];
  for (let i = 0; i <= AIR_CORE.length; i++) slots.push(i);

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-slate-700">공기 루프</h3>
        <span className="mono text-[11px] text-slate-400">드럼 → 필터 → 증발기 → 응축기 (고정) · 팬 위치 가변</span>
      </div>
      <div className="flex items-center gap-1.5 overflow-x-auto pb-2">
        {AIR_CORE.map((c, i) => {
          // 증발기/응축기는 냉매 루프에서 편집 (공기 루프선 드럼/필터만 ⚙)
          const editable = c.key === 'drum' || c.key === 'filter';
          return (
          <React.Fragment key={i}>
            {/* 팬 슬롯 (컴포넌트 앞) */}
            <FanSlot pos={i} active={fanPosition === i} onClick={setFanPosition} />
            {/* 코어 컴포넌트 */}
            <div className="shrink-0 bg-slate-50 rounded-lg border border-slate-200 px-3 py-2.5 min-w-[92px]">
              <div className="flex items-center justify-center gap-1 mb-1.5">
                <span className="text-xs font-bold text-slate-700">{c.label}</span>
                {editable && (
                  <button onClick={() => onEditParams(c.key)} title="설계변수"
                    className="text-slate-300 hover:text-slate-600 text-[11px]">⚙</button>
                )}
              </div>
              <div className="flex justify-center">
                <FidelitySelector
                  value={fidelity[c.key] || 1}
                  onChange={v => setFid(c.key, v)}
                />
              </div>
            </div>
          </React.Fragment>
          );
        })}
        {/* 마지막 슬롯 (응축기 뒤) */}
        <FanSlot pos={AIR_CORE.length} active={fanPosition === AIR_CORE.length} onClick={setFanPosition} />
      </div>
      {/* 팬 설계변수 (팬 배치 시) */}
      {fanPosition !== null && (
        <div className="mt-2">
          <button onClick={() => onEditParams('fan')}
            className="mono text-[11px] text-blue-600 hover:underline">⚙ 팬 설계변수 편집</button>
        </div>
      )}
      <div className="flex items-center gap-3 mt-3">
        <button
          onClick={() => setFanPosition(null)}
          className={`mono text-[11px] px-2 py-1 rounded border ${fanPosition === null ? 'bg-slate-100 border-slate-300 text-slate-600' : 'border-slate-200 text-slate-400 hover:bg-slate-50'}`}
        >
          팬 없음
        </button>
        <span className="mono text-[11px] text-slate-400">
          {fanPosition === null ? '팬 미배치' : `팬 위치: 슬롯 ${fanPosition}`}
        </span>
      </div>
    </div>
  );
}

function FanSlot({ pos, active, onClick }) {
  return (
    <button
      onClick={() => onClick(pos)}
      title={`슬롯 ${pos}에 팬 배치`}
      className={`fan-slot shrink-0 w-8 h-8 rounded-full border-2 border-dashed flex items-center justify-center ${active ? 'active border-blue-500' : 'border-slate-300 text-slate-400 bg-white'}`}
    >
      <span className="text-sm">{active ? '✦' : '+'}</span>
    </button>
  );
}

// ── 운전 조건 입력 ──
const FABRIC_OPTIONS = [
  { v: 'cotton', label: '면(cotton)' },
  { v: 'poly', label: '폴리(poly)' },
  { v: 'mixed', label: '혼방(mixed)' },
];

function NumberField({ label, value, unit, min, max, step, onChange }) {
  return (
    <div>
      <label className="block text-xs text-slate-500 mb-1">{label}</label>
      <div className="flex items-center gap-1.5">
        <input
          type="number" value={value} min={min} max={max} step={step || 'any'}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="mono w-full text-sm border border-slate-200 rounded-lg px-2.5 py-1.5 focus:border-blue-400 focus:outline-none"
        />
        <span className="mono text-xs text-slate-400 w-9 shrink-0">{unit}</span>
      </div>
    </div>
  );
}

function OperatingInputs({ op, setOp }) {
  const set = (k, v) => setOp({ ...op, [k]: v });
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-5">
      <h3 className="text-sm font-bold text-slate-700">운전 조건</h3>

      {/* 구동 (rpm) */}
      <div>
        <div className="mono text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">구동 속도</div>
        <div className="grid grid-cols-3 gap-3">
          <NumberField label="압축기" value={op.comp_rpm} unit="rpm" min={0} max={7200} onChange={v => set('comp_rpm', v)} />
          <NumberField label="팬" value={op.fan_rpm} unit="rpm" min={0} max={6000} onChange={v => set('fan_rpm', v)} />
          <NumberField label="드럼" value={op.drum_rpm} unit="rpm" min={0} max={120} onChange={v => set('drum_rpm', v)} />
        </div>
      </div>

      {/* 제어 (SH 타겟 → EEV PI) */}
      <div>
        <div className="mono text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">제어 목표</div>
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="과열도 타겟 (EEV PI)" value={op.SH_target} unit="K" min={0} max={30} onChange={v => set('SH_target', v)} />
          <div className="flex items-end pb-1.5">
            <span className="mono text-[10px] text-slate-400 leading-tight">EEV 개도는 SH 타겟을<br />추종해 PI 제어됩니다</span>
          </div>
        </div>
      </div>

      {/* 드럼 (포 무게 + IMC + 직물) */}
      <div>
        <div className="mono text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">드럼 초기 조건</div>
        <div className="grid grid-cols-3 gap-3">
          <NumberField label="건조 포 무게" value={op.M_dry} unit="kg" min={0.1} max={15} step={0.1} onChange={v => set('M_dry', v)} />
          <NumberField label="초기 함수율 (IMC)" value={op.X0_pct} unit="%" min={0} max={200} step={5} onChange={v => set('X0_pct', v)} />
          <div>
            <label className="block text-xs text-slate-500 mb-1">직물</label>
            <select
              value={op.fabric}
              onChange={e => set('fabric', e.target.value)}
              className="mono w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5 focus:border-blue-400 focus:outline-none bg-white"
            >
              {FABRIC_OPTIONS.map(f => <option key={f.v} value={f.v}>{f.label}</option>)}
            </select>
          </div>
        </div>
        <p className="mono text-[10px] text-slate-400 mt-1.5">
          드럼 입구 공기는 응축기 출구에서 연성으로 자동 결정됩니다 (별도 입력 불필요)
        </p>
      </div>

      {/* 동적 시뮬레이션 */}
      <div className="pt-4 border-t border-slate-100">
        <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
          <input type="checkbox" checked={op.dynamic} onChange={e => set('dynamic', e.target.checked)} className="accent-blue-600" />
          동적 시뮬레이션 (콜드스타트 — 정지→기동→정상운전)
        </label>
        {op.dynamic && (
          <div className="mt-3 pl-6 grid grid-cols-2 gap-3">
            <NumberField label="초기 냉매 평형압력" value={op.P_equalize} unit="bar" min={1} max={20} step={0.1} onChange={v => set('P_equalize', v)} />
            <NumberField label="기동 ramp 시간" value={op.ramp_time} unit="s" min={0} max={600} step={10} onChange={v => set('ramp_time', v)} />
            <NumberField label="총 해석 시간" value={op.t_end} unit="s" min={10} max={7200} step={60} onChange={v => set('t_end', v)} />
            <NumberField label="시간 스텝 (dt)" value={op.dt} unit="s" min={1} max={600} step={10} onChange={v => set('dt', v)} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── 결과 패널 (샘플 데이터) ──
function ResultsPanel({ result, running }) {
  if (!result) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col items-center justify-center min-h-[280px] text-center">
        <div className="text-4xl mb-3 opacity-20">⟳</div>
        <p className="text-sm text-slate-400">사이클을 실행하면 결과가 여기 표시됩니다</p>
        <p className="mono text-[11px] text-slate-300 mt-1">P_evap · P_cond · Q · COP · 궤적</p>
      </div>
    );
  }
  const metrics = [
    { label: '증발압력', value: result.P_evap, unit: 'bar', color: 'var(--evap)' },
    { label: '응축압력', value: result.P_cond, unit: 'bar', color: 'var(--cond)' },
    { label: '냉매유량', value: result.m_dot, unit: 'kg/s', color: 'var(--comp)' },
    { label: '응축열량', value: result.Q_cond, unit: 'W', color: 'var(--cond)' },
    { label: '증발열량', value: result.Q_evap, unit: 'W', color: 'var(--evap)' },
    { label: '과열도', value: result.SH, unit: 'K', color: 'var(--eev)' },
  ];
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-slate-700">결과</h3>
        <span className={`mono text-[11px] px-2 py-0.5 rounded ${result.converged ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
          {result.converged ? `✓ 수렴 (${result.iterations}회)` : '~ 미수렴'}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {metrics.map(m => (
          <div key={m.label} className="bg-slate-50 rounded-xl p-3">
            <div className="text-[11px] text-slate-500 mb-1">{m.label}</div>
            <div className="mono text-lg font-bold" style={{ color: m.color }}>
              {typeof m.value === 'number' ? m.value.toFixed(m.unit === 'kg/s' ? 5 : m.unit === 'bar' ? 3 : 1) : '—'}
            </div>
            <div className="mono text-[10px] text-slate-400">{m.unit}</div>
          </div>
        ))}
      </div>
      {result.trajectory && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-600 mb-2">동적 궤적 (건조 진행)</div>
          <MiniChart data={result.trajectory} />
        </div>
      )}
    </div>
  );
}

// ── 미니 궤적 차트 (SVG, 샘플) ──
function MiniChart({ data }) {
  const w = 320, h = 80, pad = 4;
  const xs = data.map(d => d.t);
  const ys = data.map(d => d.X_dry ?? 0);
  const xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  const px = t => pad + (t / xmax) * (w - 2 * pad);
  const py = x => h - pad - ((x - ymin) / (ymax - ymin || 1)) * (h - 2 * pad);
  const path = data.map((d, i) => `${i ? 'L' : 'M'}${px(d.t).toFixed(1)},${py(d.X_dry).toFixed(1)}`).join(' ');
  return (
    <svg width={w} height={h} className="w-full">
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" />
      {data.map((d, i) => (
        <circle key={i} cx={px(d.t)} cy={py(d.X_dry)} r="2.5" fill="var(--accent)" />
      ))}
      <text x={pad} y={h - 2} className="mono" fontSize="9" fill="#94a3b8">함수율 {(ymax * 100).toFixed(0)}→{(ymin * 100).toFixed(0)}%</text>
      <text x={w - 40} y={h - 2} className="mono" fontSize="9" fill="#94a3b8">{xmax}s</text>
    </svg>
  );
}

// ── 메인 앱 ──
function CycleRunner() {
  const [refFid, setRefFid] = useState({ compressor: 3, condenser: 3, eev: 3, evaporator: 3 });
  const [airFid, setAirFid] = useState({ drum: 1, filter: 1, evaporator: 3, condenser: 3, fan: 3 });
  const [fanPosition, setFanPosition] = useState(null);
  const [op, setOp] = useState({
    comp_rpm: 1800, fan_rpm: 3000, drum_rpm: 45,
    SH_target: 8.6,
    M_dry: 3.0, X0_pct: 60, fabric: 'cotton',
    dynamic: false, P_equalize: 7.0, ramp_time: 60, t_end: 1800, dt: 60,
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  // 설계변수 패널 상태 + 컴포넌트별 파라미터 오버라이드
  const [editComp, setEditComp] = useState(null);   // 열린 컴포넌트 key (null=닫힘)
  const [paramValues, setParamValues] = useState({}); // {comp: {fidelity: {name: value}}}

  const setRefFidKey = (k, v) => setRefFid({ ...refFid, [k]: v });
  const setAirFidKey = (k, v) => setAirFid({ ...airFid, [k]: v });

  // 컴포넌트 fidelity (냉매/공기 통합 조회)
  const compFidelity = (comp) => (comp in refFid) ? refFid[comp] : (airFid[comp] || 1);
  const COMP_LABELS = { compressor: '압축기', condenser: '응축기', eev: '팽창밸브', evaporator: '증발기', fan: '팬', drum: '드럼', filter: '필터' };

  // 파라미터 값 조회/변경 (comp+fidelity별)
  const getParamVals = (comp, fid) => (paramValues[comp] && paramValues[comp][fid]) || {};
  const setParamVal = (comp, fid, name, value) => {
    setParamValues(prev => ({
      ...prev,
      [comp]: { ...(prev[comp] || {}), [fid]: { ...((prev[comp] || {})[fid] || {}), [name]: value } },
    }));
  };

  // 샘플 실행 (실제로는 백엔드 API 호출)
  const runCycle = () => {
    setRunning(true);
    setResult(null);

    // 백엔드 cycle_runner 전달 payload (6단계 API 연결 시 이 형식으로 POST)
    // 단위 변환: 함수율 %→kg/kg (X0_pct/100)
    const payload = {
      ref_fidelity: refFid,        // {compressor,condenser,eev,evaporator: 1/2/3}
      air_fidelity: airFid,        // {drum,filter,fan,evaporator,condenser}
      fan_position: fanPosition,   // int | null
      operating: {
        comp_rpm: op.comp_rpm, fan_rpm: op.fan_rpm, drum_rpm: op.drum_rpm,
        SH_target: op.SH_target,   // EEV PI 제어 목표
        M_dry: op.M_dry, X0: op.X0_pct / 100, fabric: op.fabric,  // %→kg/kg
      },
      dynamic: op.dynamic,
      dynamic_opts: op.dynamic ? {
        P_equalize: op.P_equalize, ramp_time: op.ramp_time,
        t_end: op.t_end, dt: op.dt,
      } : null,
    };
    // TODO(6단계): fetch('/run_cycle_runner', {method:'POST', body: JSON.stringify(payload)})

    setTimeout(() => {
      // 샘플 결과 (백엔드 cycle_runner 반환 형식)
      const sample = {
        converged: true,
        iterations: op.dynamic ? 6 : 22,
        P_evap: 5.055 + Math.random() * 0.1,
        P_cond: 9.9 + Math.random() * 0.3,
        m_dot: 0.00206 + Math.random() * 0.0001,
        Q_cond: 570 + Math.random() * 20,
        Q_evap: 460 + Math.random() * 20,
        SH: op.SH_target + (Math.random() - 0.5) * 0.3,
      };
      if (op.dynamic) {
        // 샘플 궤적 (해석 시간 t_end까지 dt 간격, 건조율 %)
        const nPts = Math.min(12, Math.floor(op.t_end / op.dt));
        const X0 = op.X0_pct / 100;
        sample.trajectory = Array.from({ length: nPts }, (_, i) => ({
          t: (i + 1) * op.dt,
          X_dry: Math.max(0, X0 - i * 0.001),
        }));
      }
      setResult(sample);
      setRunning(false);
    }, 900);
  };

  return (
    <div className="min-h-screen">
      {/* 메뉴바 (다른 탭과 통일 — 전체 폭, border-b, AppSwitcher+상태+실행) */}
      <div className="h-9 bg-white border-b border-slate-200 flex items-center px-4 gap-4 text-[11px] shrink-0">
        <AppSwitcher current="cycle-runner" />
        <div className="text-slate-400 text-[10px]">Cycle Runner · 컴포넌트별 fidelity 자유 조합</div>
        <div className="flex-1"></div>
        <span className="mono text-[11px] text-slate-500 hidden sm:block">
          냉매 {Object.values(refFid).map(v => `L${v}`).join('·')}
        </span>
        <div className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${
          running ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-50 text-slate-500 border-slate-200'
        }`}>
          {running ? '● 실행 중' : '○ 대기'}
        </div>
      </div>

      {/* 툴바 (실행 버튼 — 다른 탭 툴바와 통일) */}
      <div className="h-11 bg-slate-50 border-b border-slate-200 flex items-center px-4 gap-3 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white text-sm font-bold">⟳</div>
          <span className="text-sm font-bold text-slate-800">Cycle Runner</span>
          <span className="mono text-[10px] text-slate-400">HPWD R290</span>
        </div>
        <div className="flex-1"></div>
        <button
          onClick={runCycle}
          disabled={running}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold px-5 py-1.5 rounded-lg flex items-center gap-2"
        >
          {running ? <><span className="animate-spin">⟳</span> 실행 중</> : <>▶ 실행</>}
        </button>
      </div>

      <main className="max-w-6xl mx-auto px-6 py-6 grid lg:grid-cols-2 gap-5">
        {/* 좌: 사이클 구성 */}
        <div className="space-y-5">
          <RefrigerantCycle fidelity={refFid} setFid={setRefFidKey} running={running} onEditParams={setEditComp} />
          <AirPath
            fidelity={airFid} setFid={setAirFidKey}
            fanPosition={fanPosition} setFanPosition={setFanPosition}
            running={running} onEditParams={setEditComp}
          />
        </div>
        {/* 우: 조건 + 결과 */}
        <div className="space-y-5">
          <OperatingInputs op={op} setOp={setOp} />
          <ResultsPanel result={result} running={running} />
        </div>
      </main>

      {/* 설계변수 패널 (컴포넌트 클릭 시) */}
      {editComp && (
        <ParamPanel
          comp={editComp}
          compLabel={COMP_LABELS[editComp] || editComp}
          fidelity={compFidelity(editComp)}
          values={getParamVals(editComp, compFidelity(editComp))}
          onChange={(name, value) => setParamVal(editComp, compFidelity(editComp), name, value)}
          onClose={() => setEditComp(null)}
        />
      )}

      <footer className="max-w-6xl mx-auto px-6 py-4 text-center">
        <p className="mono text-[10px] text-slate-300">
          UI 프로토타입 · 결과는 샘플 데이터 · 백엔드 cycle_runner 연동 예정
        </p>
      </footer>
    </div>
  );
}

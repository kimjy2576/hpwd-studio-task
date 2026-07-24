within ;
package HXGeom "핀-튜브 HX 형상 산출 — 1차 치수(W,H,D,Nr,Nt,FPI,Do,Di,fin_t,Pt,Pl)에서 파생량 계산"
  // 목적: A_i_seg / A_o_seg / A_fin_ratio / Dc / Xm / XL / A_o_face 를 하드코딩 대신 산출.
  //       격자(Nseg,Nr,Nt)나 형상을 바꿔도 파생량이 자동 추종 → 임의 구성 비교 가능.
  //
  // 출처: backend/_vendor/hx_sim/geometry.py FinTubeGeo.from_spec() 와 동일 식.
  //       2026-07-23 검증 — 증발기 기준형상에서 기존 하드코딩 7개 값을 전부 재현
  //       (최대 상대오차 0.00006%, XL 반올림 표기차).
  //
  // 규약
  //  - 핀 피치 = 0.0254/FPI [m], 핀 수 = round(W/피치)  (절삭 아님 — 실제 핀 수에 근접)
  //  - 공기측 총면적 = 핀 양면 면적 + 핀 사이 노출 튜브 외면적
  //  - 내부면적은 직선 튜브만 (U-bend는 핀이 없어 h_o≈0, 열전달 기여 미미;
  //    bend 영향은 dp에 K_bend로 별도 반영). microfin 면적증가는 A_i가 아니라
  //    EF(enhancement factor)로 반영하므로 여기서는 nominal 유지 — 이중계산 방지.

  constant Real INCH=0.0254 "[m]";

  function finPitch "핀 피치 [m]"
    input Real FPI "핀 밀도 [fins/inch]";
    output Real Pf;
  algorithm
    Pf := INCH/FPI;
    annotation(Inline=true);
  end finPitch;

  function collarD "핀 칼라 외경 [m]"
    input Real Do "튜브 외경 [m]";
    input Real fin_t "핀 두께 [m]";
    output Real Dc;
  algorithm
    Dc := Do + 2.0*fin_t;
    annotation(Inline=true);
  end collarD;

  function nFins "폭 W 구간의 핀 수 [-]"
    input Real W "튜브 길이(=코일 폭) [m]";
    input Real FPI;
    output Integer N;
  algorithm
    N := integer(floor(W/finPitch(FPI) + 0.5)) "round";
  end nFins;

  function A_face "공기측 전면적 [m2]"
    input Real W, H;
    output Real A;
  algorithm
    A := H*W;
    annotation(Inline=true);
  end A_face;

  function A_finOnly "핀 면적 합 [m2] (양면, 튜브 관통부 제외)"
    input Real W, H, D "코일 폭·높이·깊이 [m]";
    input Integer Nr, Nt "행(공기방향)·열(튜브) 수";
    input Real FPI, Do, fin_t;
    output Real A;
  protected
    Real Dc, hole;
    Integer Nfin, Ntube;
  algorithm
    Dc := collarD(Do, fin_t);
    Ntube := Nr*Nt;
    Nfin := nFins(W, FPI);
    hole := Ntube*Modelica.Constants.pi*Dc^2/4.0;
    A := Nfin*2.0*(H*D - hole);
  end A_finOnly;

  function A_tubeExt "핀 사이 노출 튜브 외면적 합 [m2]"
    input Real W, FPI, Do, fin_t;
    input Integer Nr, Nt;
    output Real A;
  protected
    Real Dc, gap;
  algorithm
    Dc := collarD(Do, fin_t);
    gap := finPitch(FPI) - fin_t;
    A := Nr*Nt*Modelica.Constants.pi*Dc*nFins(W, FPI)*gap;
  end A_tubeExt;

  function A_airTotal "공기측 총 전열면적 [m2]"
    input Real W, H, D;
    input Integer Nr, Nt;
    input Real FPI, Do, fin_t;
    output Real A;
  algorithm
    A := A_finOnly(W, H, D, Nr, Nt, FPI, Do, fin_t) + A_tubeExt(W, FPI, Do, fin_t, Nr, Nt);
  end A_airTotal;

  function A_o_seg "(행,세그)당 공기측 면적 [m2]"
    input Real W, H, D;
    input Integer Nr, Nt, Nseg;
    input Real FPI, Do, fin_t;
    output Real A;
  algorithm
    A := A_airTotal(W, H, D, Nr, Nt, FPI, Do, fin_t)/(Nr*Nt*Nseg);
  end A_o_seg;

  function A_i_seg "세그당 냉매측 면적 [m2] (직선 튜브만)"
    input Real Di "튜브 내경 [m]";
    input Real W;
    input Integer Nseg;
    output Real A;
  algorithm
    A := Modelica.Constants.pi*Di*W/Nseg;
    annotation(Inline=true);
  end A_i_seg;

  function finRatio "핀 면적비 A_fin/A_total [-] (핀효율 → eta_o 환산용)"
    input Real W, H, D;
    input Integer Nr, Nt;
    input Real FPI, Do, fin_t;
    output Real r;
  protected
    Real At;
  algorithm
    At := A_airTotal(W, H, D, Nr, Nt, FPI, Do, fin_t);
    r := if At > 0.0 then A_finOnly(W, H, D, Nr, Nt, FPI, Do, fin_t)/At else 0.9;
  end finRatio;

  function Xm_schmidt "Schmidt 등가원판 반경 파라미터 Xm [m]"
    input Real Pt "튜브 횡피치 [m]";
    output Real Xm;
  algorithm
    Xm := Pt/2.0;
    annotation(Inline=true);
  end Xm_schmidt;

  function XL_schmidt "Schmidt 등가원판 반경 파라미터 XL [m]"
    input Real Pt, Pl "횡·종 피치 [m]";
    input Boolean staggered=true "지그재그 배열 여부";
    output Real XL;
  algorithm
    XL := if staggered then sqrt((Pt/2.0)^2 + Pl^2)/2.0 else Pl/2.0;
  end XL_schmidt;

  function sigmaMin "최소자유유로비 sigma = A_c/A_fr [-]"
    input Real Pt, FPI, Do, fin_t;
    output Real sigma;
  protected
    Real Pf, gap, Dc;
  algorithm
    Pf := finPitch(FPI);
    gap := Pf - fin_t;
    Dc := collarD(Do, fin_t);
    sigma := max((Pt - Dc)*gap/(Pt*Pf), 0.1);
  end sigmaMin;

  function m_air_seg "(열,세그)당 공기 질량유량 [kg/s]"
    input Real m_air_total "코일 전체 공기유량 [kg/s]";
    input Integer Nt, Nseg;
    output Real m;
  algorithm
    m := m_air_total/(Nt*Nseg);
    annotation(Inline=true);
  end m_air_seg;

  model TestBaseline "검증 — 증발기/응축기 기준형상에서 기존 하드코딩 값 재현 확인"
    // 증발기 기준형상
    parameter Real eW=0.24, eH=0.05656, eD=0.04, eFPI=20.0, eDo=0.005, eDi=0.0046, eft=0.11e-3;
    parameter Real ePt=14.14e-3, ePl=10e-3;
    parameter Integer eNr=4, eNt=4, eNseg=10;
    final parameter Real e_Ai=A_i_seg(eDi, eW, eNseg) "기대 0.0003468318";
    final parameter Real e_Ao=A_o_seg(eW, eH, eD, eNr, eNt, eNseg, eFPI, eDo, eft) "기대 0.0048955023";
    final parameter Real e_Dc=collarD(eDo, eft) "기대 0.005220";
    final parameter Real e_Xm=Xm_schmidt(ePt) "기대 0.007070";
    final parameter Real e_XL=XL_schmidt(ePt, ePl) "기대 0.00612342";
    final parameter Real e_rat=finRatio(eW, eH, eD, eNr, eNt, eFPI, eDo, eft) "기대 0.9265582679";
    final parameter Real e_face=A_face(eW, eH) "기대 0.0135744";
    // 응축기 기준형상 (Nr=6, FPI=22, D=0.06 — 2026-07-23 D 누락 수정분 반영)
    parameter Real cW=0.24, cH=0.05656, cD=0.06, cFPI=22.0, cDo=0.005, cDi=0.0046, cft=0.11e-3;
    parameter Real cPt=14.14e-3, cPl=10e-3;
    parameter Integer cNr=6, cNt=4, cNseg=10;
    final parameter Real c_Ai=A_i_seg(cDi, cW, cNseg) "기대 0.0003468318";
    final parameter Real c_Ao=A_o_seg(cW, cH, cD, cNr, cNt, cNseg, cFPI, cDo, cft) "기대 0.0053482610";
    final parameter Real c_rat=finRatio(cW, cH, cD, cNr, cNt, cFPI, cDo, cft) "기대 0.9333809461";
  equation
    annotation(Documentation(info="<html>
<p>기대값은 HPWDevap.mo / HPWDon.mo 의 기존 하드코딩 파라미터.
전 항목이 1e-5 상대오차 내로 일치해야 함.</p>
</html>"));
  end TestBaseline;
end HXGeom;

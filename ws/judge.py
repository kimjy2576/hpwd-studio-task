import csv, sys
r=list(csv.reader(open(sys.argv[1])))
h=[c.strip('"') for c in r[0]]; g=lambda row,n: float(row[h.index(n)])
last=r[-1]; m0=g(r[1],'M_total')
d=[(g(x,'M_total')-m0)/m0*100 for x in r[1:]]
print(f"행 {len(r)-1} / t_end {last[0]} / 드리프트 {min(d):+.3f}~{max(d):+.3f}% / 종점 M {g(last,'M_total')*1000:.2f} g")
for n in ['Pc_bar','Pe_bar','SH','eevctl.n_pulse','seq.f']:
    print(f"  {n} 종점 {g(last,n):.3f}")

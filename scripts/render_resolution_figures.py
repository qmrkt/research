"""Render publication plots from frozen resolution artifacts (matplotlib 3.10.8)."""
from pathlib import Path
import csv
import hashlib
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]/'02-trust-explicit-resolution'
OUT=ROOT/'figures'; OUT.mkdir(exist_ok=True)
rows=json.loads((ROOT/'output/economy_validation/summary.json').read_text())
by={r['case']:r for r in rows}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,
 'axes.spines.right':False,'axes.labelsize':8,'axes.titlesize':9,'legend.fontsize':7,
 'pdf.fonttype':42,'svg.fonttype':'none'})
colors=['#176a78','#b34c34','#66538b','#5a7650']
fig,ax=plt.subplots(1,2,figsize=(5.5,3.1),layout='constrained')
pools=[50,500,5000,50000]
for i,(treatment,attention,label) in enumerate([('flat10','lazy','Flat 10, low attention'),('rho0.15','lazy','15% of pool, low attention'),('flat10','attentive','Flat 10, high attention'),('rho0.15','attentive','15% of pool, high attention')]):
 r=[by[f'bond_scaling/L{L}-{attention}/{treatment}'] for L in pools]
 y=[x['wrong_all_rate']*100 for x in r]
 ax[0].plot(pools,y,marker='o',ms=3,lw=1.3,color=colors[i],label=label,linestyle='-' if attention=='lazy' else '--')
 ax[0].fill_between(pools,[x['wrong_all_wilson95'][0]*100 for x in r],[x['wrong_all_wilson95'][1]*100 for x in r],color=colors[i],alpha=.1)
ax[0].set(xscale='log',xlabel='Market collateral L',ylabel='Wrong outcomes per episode (%)',title='Bond scaling and attention',ylim=(-1,70))
ax[0].legend(loc='upper left',frameon=False)
for i,(attention,label) in enumerate([('lazy','Low attention'),('stake','Stake-weighted'),('attentive','High attention')]):
 W=[2,12,24,48,72];r=[by[f'window/{attention}/w{w}'] for w in W]
 ax[1].plot(W,[x['wrong_all_rate']*100 for x in r],marker='o',ms=3,lw=1.3,color=colors[i],label=label)
 ax[1].fill_between(W,[x['wrong_all_wilson95'][0]*100 for x in r],[x['wrong_all_wilson95'][1]*100 for x in r],color=colors[i],alpha=.1)
ax[1].set(xlabel='Challenge window (hours)',ylabel='Wrong outcomes per episode (%)',title='A window buys arrivals',ylim=(-1,55))
ax[1].legend(loc='upper right',frameon=False)
for a in ax:a.grid(alpha=.17)
fig.savefig(OUT/'funded_game.pdf');fig.savefig(OUT/'funded_game.png',dpi=180);plt.close(fig)
fig,ax=plt.subplots(1,2,figsize=(5.5,3.1),layout='constrained')
rhos=[.02+i*.004 for i in range(121)]
for i,a in enumerate([.9,.95,.99]):
 ax[0].plot(rhos,[1/(a*(1+r)) for r in rhos],lw=1.4,color=colors[i],label=f'Accuracy {a:.2f}')
ax[0].axhline(1,color='#777777',ls='--',lw=.8)
ax[0].axhspan(1,1.2,color='#aaaaaa',alpha=.15)
ax[0].text(.32,1.07,'Infeasible coverage',fontsize=7,color='#555555')
ax[0].set(xlabel='Proposer bond / collateral',ylabel='Required challenge probability',title='Worst-case exposure: D = L, fee = 0',ylim=(.66,1.12))
ax[0].legend(loc='lower left',frameon=False)
labels=['Single\n5%\nerror','2 of 3\n5%\niid','2 of 3\n14.5%\niid','2 of 3\n14.5%\nshared']
vals=[.05,3*.05**2-2*.05**3,3*.145**2-2*.145**3,.1+.9*(3*.05**2-2*.05**3)]
ax[1].bar(range(4),[v*100 for v in vals],color=[colors[0],colors[1],colors[0],colors[1]],width=.65)
for i,v in enumerate(vals):ax[1].text(i,v*100+.25,f'{v*100:.3f}%',ha='center',fontsize=7)
ax[1].set(xticks=range(4),xticklabels=labels,ylabel='Wrong outcomes (%)',title='Composition and common causes',ylim=(0,12.5))
for a in ax:a.grid(axis='y',alpha=.17);a.set_axisbelow(True)
fig.savefig(OUT/'frontier_and_composition.pdf');fig.savefig(OUT/'frontier_and_composition.png',dpi=180);plt.close(fig)
manifest={'renderer':'scripts/render_resolution_figures.py','matplotlib':matplotlib.__version__,
 'economy_summary_sha256':hashlib.sha256((ROOT/'output/economy_validation/summary.json').read_bytes()).hexdigest(),
 'source_error_formulas':{'iid_majority':'3 e^2 - 2 e^3','common_shock':'.1 + .9 (3*.05^2 - 2*.05^3)','matched_source_error':'.1 + .9*.05 = .145'},
 'plots':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('*.pdf'))}}
(OUT/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')

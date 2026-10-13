"""Render the paper's selection figure from saved experiment rows and proved bounds."""
from pathlib import Path
import hashlib
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / '03-verified-execution'
SOURCE = PAPER / 'output/quorum/selection_summary.json'
rows = [r for r in json.loads(SOURCE.read_text()) if r['p'] == 0.1]
assert len(rows) == 4
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.spines.top': False,
                     'axes.spines.right': False, 'pdf.fonttype': 42})
fig, axes = plt.subplots(2, 1, figsize=(4.5, 4.7), layout='constrained')
x = list(range(1, 31))
axes[0].plot(x, [100*(1-0.9**m) for m in x], color='#246985', label='Choose best of m: exact')
axes[0].axhline(10, color='#bf6738', linestyle='--', label='Prescribed first attempt: exact')
for i, r in enumerate(rows):
    y = 100*r['unrestricted_best_of_m']; low, high = r['best_of_m_wilson95']
    axes[0].errorbar(r['attempts'], y, yerr=[[y-100*low],[100*high-y]], fmt='o',
                     color='#173846', capsize=3, label='Monte Carlo (95% Wilson)' if i==0 else None)
axes[0].set(xlabel='Number of candidate attempts', ylabel='Favorable result (%)',
            ylim=(0, 104), title='Repeated execution selects the outcome')
axes[0].legend(frameon=False, fontsize=7.5, loc='center right')
a = [i/1000 for i in range(1,1001)]
upper = [100*min(1,0.1/t) for t in a]
lower = [100*max(0,(0.1+t-1)/t) for t in a]
axes[1].fill_between([100*t for t in a], lower, upper, color='#b9d9dd', alpha=.65)
axes[1].plot([100*t for t in a],upper,color='#246985',label='Sharp maximum under suppression')
axes[1].axhline(10,color='#bf6738',linestyle='--',label='Baseline favorable probability')
axes[1].scatter([10],[100],color='#173846',s=22,zorder=3)
axes[1].set(xlabel='Requests that finalize (%)', ylabel='Favorable among finalized (%)',
            xlim=(0,100), ylim=(0,104), title='Aborts can bias the surviving sample')
axes[1].legend(frameon=False,fontsize=7.3,loc='upper right',bbox_to_anchor=(1,.82))
for ax in axes:
    ax.grid(axis='y',alpha=.2)
output=PAPER/'figures';output.mkdir(exist_ok=True)
for ext in ('pdf','png'):
    fig.savefig(output/f'selection-integrity.{ext}',dpi=180)
plt.close(fig)
manifest={'source':str(SOURCE.relative_to(ROOT)),
          'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'generator':str(Path(__file__).relative_to(ROOT)),
          'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'matplotlib':matplotlib.__version__,
          'top':'p=.1, exact 1-(1-p)^m and saved seeded Monte Carlo Wilson intervals',
          'bottom':'proved sharp bounds max(0,(p+alpha-1)/alpha) to min(1,p/alpha), p=.1; not observed field rates'}
(output/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')

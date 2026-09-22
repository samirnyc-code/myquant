import json, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.inspection import permutation_importance
np.random.seed(0)

G = json.load(open('scratchpad/bl_basket_gamma.json'))
SYMS = sorted(G.keys())
LEVELS = ['Call Resistance','Put Support','HVL','Call Resistance 0DTE','Put Support 0DTE',
          'HVL 0DTE','Gamma Wall 0DTE','1D Min','1D Max'] + [f'GEX {i}' for i in range(1,11)]

def spot(sym, dt):
    d = G.get(sym,{}).get(dt)
    if not d: return None
    mn,mx = d.get('1D Min'), d.get('1D Max')
    if mn is None or mx is None: return None
    return 0.5*(mn+mx)

def load_target(sym):
    df = pd.read_csv(f'data/menthorq/{sym}_mq_blindspots_history.csv')
    df = df.set_index('date')
    return df  # bl_1..bl_10

def build(target_sym, spot_sym):
    tgt = load_target(target_sym)
    rows, feat_rows, dates = [], [], []
    for dt in tgt.index:
        s = spot(spot_sym, dt)
        if s is None: continue
        bl = tgt.loc[dt, [f'bl_{i}' for i in range(1,11)]].values.astype(float)
        if np.any(~np.isfinite(bl)): continue
        bl_sorted = np.sort(bl)
        y = (bl_sorted - s)/s  # %-offset target, sorted
        fv = {}
        for a in SYMS:
            ad = G.get(a,{}).get(dt)
            asp = spot(a, dt)
            fv[f'{a}::spotratio'] = (asp/s) if asp else np.nan
            for lv in LEVELS:
                val = ad.get(lv) if ad else None
                fv[f'{a}::{lv}'] = ((val - s)/s) if (val is not None) else np.nan
        rows.append(y); feat_rows.append(fv); dates.append(dt)
    X = pd.DataFrame(feat_rows, index=dates)
    Y = pd.DataFrame(rows, index=dates, columns=[f'blr_{i}' for i in range(1,11)])
    return X, Y, tgt.index

def run(target_sym, spot_sym, label):
    X, Y, _ = build(target_sym, spot_sym)
    n = len(X)
    ntr = 140
    # time-based split
    Xtr, Xte = X.iloc[:ntr], X.iloc[ntr:]
    Ytr, Yte = Y.iloc[:ntr], Y.iloc[ntr:]
    # spot for test set (to convert %-offset MAE back to points)
    spots_te = np.array([spot(spot_sym, dt) for dt in Xte.index])

    # impute with TRAIN median (no leakage), drop all-nan cols
    med = Xtr.median()
    keep = med.dropna().index
    Xtr_i = Xtr[keep].fillna(med[keep])
    Xte_i = Xte[keep].fillna(med[keep])

    out = {'label':label,'n':n,'ntr':ntr,'nte':len(Xte),'nfeat':len(keep)}

    # ---- baselines ----
    # (i) climatology: predict train-mean %-offset per rank
    clim = Ytr.mean().values  # (10,)
    # (ii) SPX/SPY/QQQ-only Ridge
    idx3 = [c for c in keep if c.split('::')[0] in ('SPX','SPY','QQQ')]
    # ---- models ----
    def mae_points(pred, rank):
        # pred, Yte[rank] are %-offsets; convert to points via test spot
        err = np.abs((pred - Yte.iloc[:,rank].values)*spots_te)
        return err.mean()

    res = {}
    per_bl = {}
    for rank in range(10):
        ytr = Ytr.iloc[:,rank].values
        yte = Yte.iloc[:,rank].values
        # climatology
        mae_clim = np.abs((clim[rank]-yte)*spots_te).mean()
        # 3-asset ridge
        r3 = Ridge(alpha=1.0).fit(Xtr_i[idx3], ytr)
        p3 = r3.predict(Xte_i[idx3])
        mae_3 = np.abs((p3-yte)*spots_te).mean()
        p3tr = r3.predict(Xtr_i[idx3]); mae_3tr = np.abs((p3tr-ytr)*[spot(spot_sym,dt) for dt in Xtr_i.index]).mean()
        # full basket RF
        rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.3, n_jobs=-1, random_state=0)
        rf.fit(Xtr_i, ytr)
        pf = rf.predict(Xte_i)
        mae_full = np.abs((pf-yte)*spots_te).mean()
        pftr = rf.predict(Xtr_i); mae_fulltr = np.abs((pftr-ytr)*[spot(spot_sym,dt) for dt in Xtr_i.index]).mean()
        # GBM full
        gb = GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0)
        gb.fit(Xtr_i, ytr); pg = gb.predict(Xte_i)
        mae_gb = np.abs((pg-yte)*spots_te).mean()
        per_bl[rank] = dict(clim=mae_clim, spx_spy_qqq=mae_3, rf_full=mae_full, gb_full=mae_gb,
                            rf_train=mae_fulltr, ridge3_train=mae_3tr)
    out['per_bl'] = per_bl

    # aggregate
    agg = {k: np.mean([per_bl[r][k] for r in range(10)]) for k in ['clim','spx_spy_qqq','rf_full','gb_full','rf_train']}
    out['agg'] = agg

    # ---- permutation importance on a pooled model (stack ranks) ----
    # Fit one RF on middle rank (rank 5) as representative + aggregate importances across ranks via RF feature_importances_
    imp_accum = np.zeros(len(keep))
    for rank in range(10):
        rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.3, n_jobs=-1, random_state=0)
        rf.fit(Xtr_i, Ytr.iloc[:,rank].values)
        imp_accum += rf.feature_importances_
    imp = pd.Series(imp_accum/10, index=keep).sort_values(ascending=False)
    out['top_features'] = imp.head(20).to_dict()
    # by asset
    asset_imp = imp.groupby(lambda c: c.split('::')[0]).sum().sort_values(ascending=False)
    out['asset_imp'] = asset_imp.to_dict()
    # by level type
    lvl_imp = imp.groupby(lambda c: c.split('::')[1]).sum().sort_values(ascending=False)
    out['level_imp'] = lvl_imp.to_dict()

    # ---- nearest-feature attribution stability ----
    # For each actual sorted BL each day, which feature (asset::level, offset) is nearest? Is it stable?
    attr = []
    feat_cols = [c for c in keep if not c.endswith('spotratio')]
    Xall = X[feat_cols]
    for dt in X.index:
        s = spot(spot_sym, dt)
        bl = load_target(target_sym).loc[dt,[f'bl_{i}' for i in range(1,11)]].values.astype(float)
        if np.any(~np.isfinite(bl)): continue
        bl_sorted = np.sort(bl)
        yoff = (bl_sorted - s)/s
        frow = Xall.loc[dt]
        for rank in range(10):
            diffs = (frow - yoff[rank]).abs()
            if diffs.dropna().empty: continue
            nf = diffs.idxmin()
            attr.append((rank, nf, diffs.min()*s))  # points error
    adf = pd.DataFrame(attr, columns=['rank','feat','pts'])
    # stability: for each rank, modal feature share
    stab = {}
    for rank in range(10):
        sub = adf[adf['rank']==rank]
        if len(sub)==0: continue
        vc = sub['feat'].value_counts(normalize=True)
        stab[rank] = dict(top_feat=vc.index[0], share=round(float(vc.iloc[0]),3),
                          median_pts=round(float(sub['pts'].median()),2), n=len(sub))
    out['attribution'] = stab
    return out

import sys
results = {}
for tsym, ssym, lab in [('ES1!','ES1!','ES'), ('NQ1!','NQ1!','NQ')]:
    results[lab] = run(tsym, ssym, lab)

json.dump(results, open('scratchpad/bl_formula_ml_results.json','w'), indent=2, default=str)
# print summary
for lab,o in results.items():
    print('='*60); print(lab, 'n=',o['n'],'ntr=',o['ntr'],'nte=',o['nte'],'nfeat=',o['nfeat'])
    print('AGG MAE (pts): clim=%.2f  spx/spy/qqq=%.2f  rf_full=%.2f  gb_full=%.2f  rf_TRAIN=%.2f'%(
        o['agg']['clim'],o['agg']['spx_spy_qqq'],o['agg']['rf_full'],o['agg']['gb_full'],o['agg']['rf_train']))
    print('per-BL (rank: clim / spx3 / rf_full / gb):')
    for r in range(10):
        p=o['per_bl'][r]; print('  bl%2d: %.2f / %.2f / %.2f / %.2f'%(r+1,p['clim'],p['spx_spy_qqq'],p['rf_full'],p['gb_full']))
    print('TOP ASSETS:', list(o['asset_imp'].items())[:8])
    print('TOP LEVELS:', list(o['level_imp'].items())[:8])
    print('TOP FEATS:', list(o['top_features'].items())[:10])
